from __future__ import annotations

import logging
import os
from collections import defaultdict

from pyan.analyzer import CallGraphVisitor
from pyan.modvis import ImportVisitor
from pyan.node import Flavor

from pytest_regsmart.const import DEFAULT_DIFF_LEVEL, DIFF_LEVEL

from ..utils import _find_py_files
from .dynamic_dispatch import get_dynamic_method_dependencies
from .git_manager import resolve_repo
from .models import (
    _KEPT_FLAVORS,
    DependenciesMap,
    DependencyGraph,
    DependentsMap,
    FunctionMetadata,
    FunctionNodes,
    FunctionsByFile,
    ModuleToPath,
    _ModuleQualifiedCallGraphVisitor,
)

_logger = logging.getLogger(__name__)

#use the pyan3 API, not the CLI

_MAX_SKIPPED_FILES = 200  # teto de arquivos ignorados por SyntaxError antes de desistir

    
def _normalize_pyan_module_name(module_name: str) -> str:
    """Normalize pyan's special module name for package ``__init__`` files."""
    return module_name.replace(".__init__.", ".").removesuffix(".__init__")


def _stub_modules_by_public_name(graph: CallGraphVisitor) -> dict[str, str]:
    """Map importable module names to pyan scopes for matching ``.pyi`` files."""
    result = {}
    for module_name, filename in graph.module_to_filename.items():
        if filename.endswith(".pyi"):
            public_name = _normalize_pyan_module_name(module_name.removesuffix(".pyi"))
            result[public_name] = module_name
    return result


def _resolve_imported_function(
    node,
    graph: CallGraphVisitor,
    function_nodes: FunctionNodes,
    stub_modules: dict[str, str],
    seen: set[tuple[str, str]] | None = None,
) -> str | None:
    """Resolve a pyan import binding through analyzed module and stub scopes."""
    node_name = node.get_name()
    if node_name in function_nodes:
        return node_name
    if node.flavor != Flavor.IMPORTEDITEM or node.namespace is None:
        return None

    module_name = _normalize_pyan_module_name(node.namespace)
    symbol_name = node.name
    key = (module_name, symbol_name)
    if seen is None:
        seen = set()
    if key in seen:
        return None
    seen.add(key)

    candidate = f"{module_name}.{symbol_name}"
    if candidate in function_nodes:
        return candidate

    # Prefer a stub scope when available: it describes public exports that may
    # be created dynamically by the runtime package __init__.py.
    scope_names = [stub_modules.get(module_name), module_name]
    for scope_name in scope_names:
        scope = graph.scopes.get(scope_name) if scope_name else None
        binding = scope.defs.get(symbol_name) if scope is not None else None
        if binding is None or binding is node:
            continue
        resolved = _resolve_imported_function(
            binding, graph, function_nodes, stub_modules, seen
        )
        if resolved is not None:
            return resolved
    return None


def _resolve_qualified_function_target(
    target_name: str,
    graph: CallGraphVisitor,
    function_nodes: FunctionNodes,
    stub_modules: dict[str, str],
) -> str | None:
    """Resolve a qualified public name to a function node without name-only matching."""
    if target_name in function_nodes:
        return target_name

    parts = target_name.split(".")
    for module_end in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:module_end])
        symbol_path = parts[module_end:]
        if len(symbol_path) != 1:
            continue

        scope_names = [stub_modules.get(module_name), module_name]
        for scope_name in scope_names:
            scope = graph.scopes.get(scope_name) if scope_name else None
            binding = scope.defs.get(symbol_path[0]) if scope is not None else None
            if binding is None:
                continue
            resolved = _resolve_imported_function(
                binding, graph, function_nodes, stub_modules
            )
            if resolved is not None:
                return resolved
    return None


def _extract_function_nodes(
    graph: CallGraphVisitor,
    working_dir: str,
) -> tuple[FunctionNodes, FunctionsByFile]:
    """Filters and converts pyan3 nodes into simpler function nodes indexed by name"""

    function_nodes: FunctionNodes = {}
    functions_by_file: FunctionsByFile = defaultdict(set)

    for node_group in graph.nodes.values():
        for node in node_group:
            if (
                node.flavor not in _KEPT_FLAVORS
                or node.ast_node is None
                or node.filename.endswith(".pyi")
            ):
                continue

            filepath = os.path.relpath(node.filename, working_dir)
            if filepath.startswith(".."):
                continue

            function_name = node.get_name()  #combines the module (node.namespace) and the function name (node.name)
            function_nodes[function_name] = FunctionMetadata(
                filepath=filepath,
                start_line=node.ast_node.lineno,
                end_line=node.ast_node.end_lineno,
            )
            functions_by_file[filepath].add(function_name)

    return function_nodes, dict(functions_by_file)


def _convert_module_to_relative_path(fullpaths: ModuleToPath, working_dir: str) -> ModuleToPath:
    """Convert pyan3 module names to paths relative to the repo (to match the diff).

    E.g.: "pytest_regsmart.selector" -> "pytest_regsmart/selector.py"
    """
    return {
        module: os.path.relpath(fullpath, working_dir)
        for module, fullpath in fullpaths.items()
    }


def _build_import_name_to_path(fullpaths: ModuleToPath, working_dir: str) -> dict[str, str]:
    """Map every possible import-style suffix of a module's dotted name to its file path.

    E.g. for module "src.text_toolkit.text_stats":
      "text_stats" -> path
      "text_toolkit.text_stats" -> path
      "src.text_toolkit.text_stats" -> path (redundant with module_to_path, harmless)

    For __init__ modules, the __init__ segment is dropped so that the package
    name itself maps to the __init__.py file:
      "src.text_toolkit.__init__" -> segments become ["src", "text_toolkit"]
      "text_toolkit" -> path
      "src.text_toolkit" -> path

    __init__ modules take priority over regular modules for the same import name,
    matching Python's import resolution semantics (from pkg import X resolves to
    pkg/__init__.py, not pkg/X.py).

    Ambiguous suffixes (same suffix pointing to different non-init files) are
    dropped entirely.
    """
    import_to_path: dict[str, str] = {}
    ambiguous: set[str] = set()

    for module, fullpath in fullpaths.items():
        rel_path = os.path.relpath(fullpath, working_dir)
        segments = module.split(".")
        is_init = segments[-1] == "__init__"
        if is_init:
            segments = segments[:-1]

        for i in range(len(segments)):
            candidate = ".".join(segments[i:])
            existing = import_to_path.get(candidate)
            if existing is None or is_init:
                import_to_path[candidate] = rel_path
            elif existing != rel_path:
                ambiguous.add(candidate)

    for name in ambiguous:
        import_to_path.pop(name, None)

    return import_to_path


def _invert_dependency_map(
        connections: DependenciesMap,
        module_to_path: ModuleToPath | None = None, # only necessary for file-level graphs
        import_name_to_path: dict[str, str] | None = None, # fallback for import-style names that don't match path-derived module names (ImportVisitor problem)
    ) -> DependentsMap:
    """Invert 'Y imports X' into 'X is used by Y'.

    E.g.: if plugin.py imports selector.py, the result contains
    selector.py -> {plugin.py} (changing selector.py affects plugin.py); OR changing run affects test_run()

    With module_to_path: translates module names to relative paths (file-level graph)
        e.g.: "pytest_regsmart.selector" -> "pytest_regsmart/selector.py"
    Without module_to_path: keeps ids (functions references) as-is (function-level graph)
        e.g.: "pytest_regsmart.selector:selector" -> "pytest_regsmart.selector:plugin" (changing selector affects plugin)
    """

    dependents = defaultdict(set) #dict that does not raise KeyError on missing keys; a dict subclass: https://www.geeksforgeeks.org/python/defaultdict-in-python/

    for importer, dependencies in connections.items():
        importer_path = importer if module_to_path is None else module_to_path.get(importer)
        if importer_path is None:
            continue  #importer is not in the repo - just a precaution, should not happen

        for imported in dependencies:
            imported_path = imported if module_to_path is None else module_to_path.get(imported)
            if imported_path is None and import_name_to_path is not None:
                imported_path = import_name_to_path.get(imported)
            if imported_path is None:
                continue  #doesnt import a file in the repo
            dependents[imported_path].add(importer_path)

    return dict(dependents)


def _build_file_dependency_graph(
    python_files: list[str],
    working_dir: str,
) -> DependencyGraph:
    graph = ImportVisitor(filenames=python_files, logger=logging.getLogger(__name__), root=working_dir)
    #graph.modules: module -> set of modules imported by it
    #graph.fullpaths: module -> absolute file path

    module_to_path = _convert_module_to_relative_path(graph.fullpaths, working_dir)
    import_name_to_path = _build_import_name_to_path(graph.fullpaths, working_dir)
    dependents = _invert_dependency_map(graph.modules, module_to_path, import_name_to_path)  # invert so it becomes module -> who IMPORTS it / who is affected by it

    return DependencyGraph(dependents=dependents)


def _build_function_dependency_graph(
    python_files: list[str],
    working_dir: str,
) -> DependencyGraph:
    graph = _ModuleQualifiedCallGraphVisitor(
        filenames=python_files,
        root=working_dir,
        logger=logging.getLogger(__name__),
    )

    function_nodes, functions_by_files = _extract_function_nodes(graph, working_dir)

    function_dependencies: defaultdict[str, set[str]] = defaultdict(set)

    for function_node, dependency_nodes in graph.uses_edges.items():
        function_name = function_node.get_name()
        if function_name not in function_nodes:
            continue  #skip nodes that are not functions/methods/classes

        for dependency in dependency_nodes:
            dependency_name = dependency.get_name()
            if dependency_name in function_nodes:
                function_dependencies[function_name].add(dependency_name)

    stub_modules = _stub_modules_by_public_name(graph)
    for caller, qualified_target in graph.module_qualified_calls:
        if caller not in function_nodes:
            continue
        # Keep pyan's direct call edge when it already resolved this target.
        if qualified_target in function_dependencies[caller]:
            continue
        # Resolve only qualified calls that pyan did not already represent.
        target = _resolve_qualified_function_target(
            qualified_target, graph, function_nodes, stub_modules
        )
        if target is not None:
            function_dependencies[caller].add(target)

    # pyan resolves the statically visible method on ``self``/``cls``. Add
    # conservative dynamic-dispatch edges for overrides in known subclasses,
    # and resolve calls on locals that are directly constructed in a function.
    # This is deliberately a single-function analysis: it does not propagate
    # inferred types across calls or guess from method names alone.
    def resolve_imported_class(
        module_name: str,
        symbol_name: str,
        local_scope: str | None,
    ) -> str | None:
        scope_names = (
            local_scope,
            stub_modules.get(module_name),
            module_name,
            f"{module_name}.__init__",
        )
        for scope_name in scope_names:
            scope = graph.scopes.get(scope_name) if scope_name else None
            binding = scope.defs.get(symbol_name) if scope is not None else None
            if binding is not None:
                resolved = _resolve_imported_function(
                    binding, graph, function_nodes, stub_modules
                )
                if resolved:
                    return resolved
        return None

    try:
        dynamic_dependencies = get_dynamic_method_dependencies(
            python_files, graph, function_nodes, resolve_imported_class
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "regsmart: ignoring inheritance-based dependencies (%s)",
            type(exc).__name__,
        )
    else:
        for caller, targets in dynamic_dependencies.items():
            function_dependencies[caller].update(targets)

    dependents = _invert_dependency_map(function_dependencies) #function_dependencies already have the function names, so no need to convert to paths

    return DependencyGraph(
        dependents=dependents,
        function_nodes=function_nodes,
        functions_by_file=functions_by_files
    )


def _readable_python_files(python_files: list[str]) -> list[str]:
    """Discards every .py file unreadble by pyan3 - that only decodes uft-8"""
    readable = []
    for path in python_files:
        try:
            with open(path, encoding="utf-8") as f:
                f.read()
        except (UnicodeDecodeError, OSError) as exc:
            _logger.warning("regsmart: ignoring %s at the dependency graph (%s)", path, type(exc).__name__)
            continue
        readable.append(path)
    return readable


def get_dependency_graph(
    repo_path: str = ".",
    graph_level: DIFF_LEVEL = DEFAULT_DIFF_LEVEL,
) -> DependencyGraph:
    repo = resolve_repo(repo_path)
    working_dir = repo.working_tree_dir
    python_files = _readable_python_files(
        _find_py_files(
            working_dir,
            include_stubs=graph_level == DIFF_LEVEL.FUNCTION,
        )
    )

    build = (
        _build_function_dependency_graph
        if graph_level == DIFF_LEVEL.FUNCTION
        else _build_file_dependency_graph
    )

    # unparseable files (templates, python2 code, intentionally bug fixtures
    #  also crash pyan3 - this logic removes the offending
    # file and tries again, up to a limit of _MAX_SKIPPED_FILES
    for _ in range(_MAX_SKIPPED_FILES + 1):
        try:
            return build(python_files, working_dir)
        except SyntaxError as exc:
            bad = os.path.normpath(exc.filename) if exc.filename else None
            remaining = [f for f in python_files if os.path.normpath(f) != bad]
            if bad is None or len(remaining) == len(python_files):
                raise
            _logger.warning("regsmart: ignorando %s no grafo de dependências (SyntaxError)", bad)
            python_files = remaining
    raise RuntimeError(f"mais de {_MAX_SKIPPED_FILES} arquivos não puderam ser analisados pelo pyan3")
