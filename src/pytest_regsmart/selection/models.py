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


class _ModuleQualifiedCallGraphVisitor(CallGraphVisitor):
    """CallGraphVisitor with a narrow fallback for qualified module calls.

    pyan already resolves the imported root name in the current scope. Keep
    the remaining attribute path while the original Call AST is being visited,
    so lazy package attributes can be matched to a known function node later.
    """

    def __init__(self, *args, **kwargs):
        self.module_qualified_calls: set[tuple[str, str]] = set()
        # (caller, dotted name) for module references passed as call arguments,
        # e.g. ``doctest.testmod(pkg.mod)``: the callee exercises the whole module.
        self.module_arguments: set[tuple[str, str]] = set()
        self._local_import_stack: list[set[str]] = []
        # Roots bound by ``import a.b`` (without ``as``) in the current file:
        # pyan leaves ``a`` without a value, but it is the top-level package.
        self._dotted_import_roots: set[str] = set()
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

    def visit_Call(self, node: ast.Call):
        target = node.func
        attributes: list[str] = []
        while isinstance(target, ast.Attribute):
            attributes.append(target.attr)
            target = target.value

        if isinstance(target, ast.Name) and attributes:
            root_name = target.id
            scope = self.scope_stack[-1]
            root_value = self.get_value(root_name)

            # Do not use a module import if the call's scope binds that name to
            # a local value (for example, a parameter named ``librosa``).
            if (
                root_name not in scope.locals
                and root_value is not None
                and root_value.flavor == Flavor.MODULE
            ):
                caller = self.get_node_of_current_namespace().get_name()
                qualified_target = ".".join(
                    [root_value.get_name(), *reversed(attributes)]
                )
                self.module_qualified_calls.add((caller, qualified_target))

        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        for argument in arguments:
            if isinstance(argument, ast.Starred):
                argument = argument.value
            reference = self._module_reference(argument)
            if reference is not None:
                caller = self.get_node_of_current_namespace().get_name()
                self.module_arguments.add((caller, reference))

        return super().visit_Call(node)
