import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

from pyan.analyzer import CallGraphVisitor
from pyan.node import Flavor

# for git momdule
LineRange: TypeAlias = tuple[int, int]
ChangedLineRanges: TypeAlias = dict[str, list[LineRange]]


@dataclass
class DiffResult:
    used_branch: str
    modified_files: list[str] = field(default_factory=list) #staged+unstaged
    untracked_files: list[str] = field(default_factory=list) #brand new files - maybe add a future flag to look only at unstaged+untracked tests
    deleted_files: list[str] = field(default_factory=list)
    changed_line_ranges: ChangedLineRanges = field(default_factory=dict)  #only for DIFF_LEVEL.FUNCTION
    no_merge_base: bool = False  #base resolved, but no shared history with HEAD


class DIFF_LEVEL(str, Enum):
    """The level at which the diff is identified."""
    FUNCTION = "function"
    FILE = "file"

    def __str__(self) -> str:
        return self.value


class DIFF_SOURCE(str, Enum):
    COMMIT = "commit"        #for CI envs - compares the merge base with HEAD
    WORKTREE = "worktree"    #for local envs - compares the merge base with the working tree and includes untracked files

    def __str__(self) -> str:
        return self.value

# for dependency graph module


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
    subprocess_tests: set[str] = field(default_factory=set)


class _QuietScopes(dict):
    """``dict`` of pyan scopes with a constant-size ``repr``.

    pyan logs ``f"Scopes now: {self.scopes}"`` once per analyzed file and pass.
    The f-string is built even when debug logging is off, so formatting every
    scope seen so far makes graph construction quadratic in the number of
    files. Only that message text changes; lookups behave as a plain dict.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return f"<{len(self)} scopes>"


class _ModuleQualifiedCallGraphVisitor(CallGraphVisitor):
    """CallGraphVisitor with a narrow fallback for qualified module references.

    pyan already resolves the imported root name in the current scope. Keep
    the remaining attribute path while the original AST is being visited, so
    lazy package attributes can be matched to a known function node later.
    Both calls (``pkg.mod.f()``) and references used as values
    (``g = pkg.mod.f``, ``pytest.raises(E, pkg.mod.f)``) are recorded.
    """

    def __init__(self, *args, **kwargs):
        self.module_qualified_calls: set[tuple[str, str]] = set()
        # (caller, dotted name) of module references passed as call arguments,
        # e.g. ``doctest.testmod(pkg.mod)``: the callee exercises the whole module.
        self.module_arguments: set[tuple[str, str]] = set()
        # Names imported inside each function being visited (innermost last).
        self._local_import_stack: list[set[str]] = []
        # Roots bound by ``import a.b`` (without ``as``) in the current file:
        # pyan leaves ``a`` without a value, but it is the top-level package.
        self._dotted_import_roots: set[str] = set()
        # short name -> [node list it indexes, entries indexed, namespace -> node]
        self._node_index: dict[str, list] = {}
        super().__init__(*args, **kwargs)

    def visit_Module(self, node):
        self._dotted_import_roots = {
            alias.name.split(".")[0]
            for statement in ast.walk(node)
            if isinstance(statement, ast.Import)
            for alias in statement.names
            if alias.asname is None and "." in alias.name
        }
        return super().visit_Module(node)

    @staticmethod
    def _imported_names(node: ast.AST) -> set[str]:
        names: set[str] = set()
        for statement in ast.walk(node):
            if isinstance(statement, ast.Import):
                names.update(
                    alias.asname or alias.name.split(".")[0] for alias in statement.names
                )
            elif isinstance(statement, ast.ImportFrom):
                names.update(alias.asname or alias.name for alias in statement.names)
        return names

    def visit_FunctionDef(self, node):
        self._local_import_stack.append(self._imported_names(node))
        try:
            return super().visit_FunctionDef(node)
        finally:
            self._local_import_stack.pop()

    def visit_AsyncFunctionDef(self, node):
        self._local_import_stack.append(self._imported_names(node))
        try:
            return super().visit_AsyncFunctionDef(node)
        finally:
            self._local_import_stack.pop()

    def _module_reference(self, expression: ast.AST) -> str | None:
        """Dotted name of ``expression`` when its root name is bound to a module."""
        attributes: list[str] = []
        while isinstance(expression, ast.Attribute):
            attributes.append(expression.attr)
            expression = expression.value
        if not isinstance(expression, ast.Name):
            return None
        root_name = expression.id
        scope = self.scope_stack[-1]
        if root_name in scope.locals and not (
            self._local_import_stack and root_name in self._local_import_stack[-1]
        ):
            # A local name (e.g. a parameter called ``pkg``) shadows the module;
            # only a function-local ``import pkg`` keeps it a module reference.
            return None
        root_value = self.get_value(root_name)
        if root_value is None and root_name in self._dotted_import_roots:
            return ".".join([root_name, *reversed(attributes)])
        if root_value is None or root_value.flavor != Flavor.MODULE:
            return None
        return ".".join([root_value.get_name(), *reversed(attributes)])

    def visit_Attribute(self, node: ast.Attribute):
        # A function referenced without being called still runs later through
        # whoever receives it (alias, argument, list element, parametrize...).
        if isinstance(node.ctx, ast.Load):
            self._record_module_qualified(node)
        return super().visit_Attribute(node)

    def get_node(self, namespace, name, ast_node=None, flavor=Flavor.UNSPECIFIED):
        """pyan's ``get_node`` without its linear scan of same-named nodes.

        pyan returns the first node of ``graph.nodes[name]`` whose namespace
        matches, creating one when none does. Node lists only grow by
        ``append`` or are replaced by new lists, and a node's namespace never
        changes, so a per-list index of first nodes by namespace is exact; a
        replaced list is re-indexed.
        """
        nodes = self.nodes.get(name)
        if nodes:
            entry = self._node_index.get(name)
            if entry is None or entry[0] is not nodes:
                entry = [nodes, 0, {}]
                self._node_index[name] = entry
            if entry[1] < len(nodes):
                by_namespace = entry[2]
                for node in nodes[entry[1]:]:
                    by_namespace.setdefault(node.namespace, node)
                entry[1] = len(nodes)
            node = entry[2].get(namespace)
            if node is not None:
                if Flavor.specificity(flavor) > Flavor.specificity(node.flavor):
                    node.flavor = flavor
                return node
        return super().get_node(namespace, name, ast_node, flavor)

    # pyan assigns ``self.scopes = {}`` during initialization; the property
    # wraps whatever it assigns, independent of the pyan version.
    @property
    def scopes(self) -> dict:
        return self.__dict__["_regsmart_scopes"]

    @scopes.setter
    def scopes(self, value: dict) -> None:
        if not isinstance(value, _QuietScopes):
            value = _QuietScopes(value)
        self.__dict__["_regsmart_scopes"] = value

    def visit_Call(self, node: ast.Call):
        self._record_module_qualified(node.func)
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            if isinstance(argument, ast.Starred):
                argument = argument.value
            reference = self._module_reference(argument)
            if reference is not None:
                caller = self.get_node_of_current_namespace().get_name()
                self.module_arguments.add((caller, reference))
        return super().visit_Call(node)

    def _record_module_qualified(self, target) -> None:
        attributes: list[str] = []
        while isinstance(target, ast.Attribute):
            attributes.append(target.attr)
            target = target.value

        if isinstance(target, ast.Name) and attributes:
            root_name = target.id
            scope = self.scope_stack[-1]
            root_value = self.get_value(root_name)

            # Do not use a module import if the scope binds that name to a
            # local value (for example, a parameter named ``librosa``).
            if root_name in scope.locals:
                return
            if root_value is not None and root_value.flavor == Flavor.MODULE:
                root_module = root_value.get_name()
            elif root_value is None and root_name in self._dotted_import_roots:
                # ``import pkg.mod`` binds ``pkg``, but pyan leaves it without a
                # value, so ``pkg.mod.f()`` would otherwise get no edge.
                root_module = root_name
            else:
                return
            caller = self.get_node_of_current_namespace().get_name()
            qualified_target = ".".join([root_module, *reversed(attributes)])
            self.module_qualified_calls.add((caller, qualified_target))
