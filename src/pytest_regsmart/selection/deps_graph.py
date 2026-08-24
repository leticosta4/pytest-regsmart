from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TypeAlias

from pyan.analyzer import CallGraphVisitor
from pyan.modvis import ImportVisitor
from pyan.node import Flavor

from pytest_regsmart.const import DEFAULT_DIFF_LEVEL, DIFF_LEVEL

from ..utils import _find_py_files
from .git_manager import resolve_repo

#initially I'll try the simplest form using only files; functions are not needed yet
#use the pyan3 API, not the CLI

_KEPT_FLAVORS = {
    Flavor.FUNCTION,
    Flavor.METHOD,
    Flavor.CLASSMETHOD,
    Flavor.STATICMETHOD,
    Flavor.CLASS,
}  #only functions, methods and classes on the fucntion callgraph (classes because of internal methods that can be desconsidered in git diff)


@dataclass(frozen=True, slots=True)
class FunctionMetadata:
    filepath: str
    start_line: int
    end_line: int


NodeId: TypeAlias = str #file or function level according to diff-level
DependenciesMap: TypeAlias = dict[NodeId, set[NodeId]]  # node -> who it depends on
DependentsMap: TypeAlias = dict[NodeId, set[NodeId]]    # node -> who depends on it
FunctionNodes: TypeAlias = dict[str, FunctionMetadata]
FunctionsByFile: TypeAlias = dict[str, set[str]]
ModuleToPath: TypeAlias = dict[str, str]


@dataclass
class DependencyGraph:
    dependents: DependentsMap  #key: module (file level) or function_id (function level), value: set of modules that depend on / are affected by it
    function_nodes: FunctionNodes = field(default_factory=dict)  #the key represents the funcion name/node name
    functions_by_file: FunctionsByFile = field(default_factory=dict)

    
def _extract_function_nodes(
    graph: CallGraphVisitor,
    working_dir: str,
) -> tuple[FunctionNodes, FunctionsByFile]:
    """Filters and converts pyan3 nodes into simpler function nodes indexed by name"""

    function_nodes: FunctionNodes = {}
    functions_by_file: FunctionsByFile = defaultdict(set)

    for node_group in graph.nodes.values():
        for node in node_group:
            if node.flavor not in _KEPT_FLAVORS or node.ast_node is None:
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


def _invert_dependency_map(
        connections: DependenciesMap,
        module_to_path: ModuleToPath | None = None # only necessary for file-level graphs
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
    dependents = _invert_dependency_map(graph.modules, module_to_path)  # invert so it becomes module -> who IMPORTS it / who is affected by it

    return DependencyGraph(dependents=dependents)


def _build_function_dependency_graph(
    python_files: list[str],
    working_dir: str,
) -> DependencyGraph:
    graph = CallGraphVisitor(
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

    dependents = _invert_dependency_map(function_dependencies) #function_dependencies already have the function names, so no need to convert to paths

    return DependencyGraph(
        dependents=dependents,
        function_nodes=function_nodes,
        functions_by_file=functions_by_files
    )


def get_dependency_graph(
    repo_path: str = ".",
    graph_level: DIFF_LEVEL = DEFAULT_DIFF_LEVEL,
) -> DependencyGraph:
    repo = resolve_repo(repo_path)
    working_dir = repo.working_tree_dir
    python_files = _find_py_files(working_dir)

    if graph_level == DIFF_LEVEL.FUNCTION:
        return _build_function_dependency_graph(python_files, working_dir)
    
    return _build_file_dependency_graph(python_files, working_dir)
