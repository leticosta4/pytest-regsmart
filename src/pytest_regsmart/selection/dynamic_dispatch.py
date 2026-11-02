from __future__ import annotations

import ast
import os
from collections import defaultdict, deque
from collections.abc import Callable

from pyan.analyzer import CallGraphVisitor
from pyan.node import Flavor

from .models import FunctionNodes


def _module_name(module: str) -> str:
    return module.replace(".__init__.", ".").removesuffix(".__init__")


def _import_bindings(
    statement: ast.Import | ast.ImportFrom,
    module: str,
    is_package: bool,
) -> dict[str, str]:
    if isinstance(statement, ast.Import):
        return {
            alias.asname or alias.name.split(".")[0]: (
                alias.name if alias.asname else alias.name.split(".")[0]
            )
            for alias in statement.names
        }

    if statement.level:
        package = module.split(".") if is_package else module.split(".")[:-1]
        package = package[: max(0, len(package) - statement.level + 1)]
        base = [*package, *([statement.module] if statement.module else [])]
    else:
        base = [statement.module] if statement.module else []
    return {
        alias.asname or alias.name: ".".join([*base, alias.name])
        for alias in statement.names
    }


class _DynamicDispatchVisitor(ast.NodeVisitor):
    def __init__(
        self,
        module: str,
        imports: dict[str, str],
        classes: set[str],
        bases: dict[str, set[str]],
        descendants: dict[str, set[str]],
        function_nodes: FunctionNodes,
        resolve_imported_class: Callable[[str, str, str | None], str | None],
        is_package: bool,
    ) -> None:
        self.module = module
        self.imports = imports
        self.classes = classes
        self.bases = bases
        self.descendants = descendants
        self.function_nodes = function_nodes
        self.resolve_imported_class = resolve_imported_class
        self.is_package = is_package
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.local_types: dict[str, str] = {}
        self.local_imports: dict[str, str] = {}
        self.dependencies: defaultdict[str, set[str]] = defaultdict(set)

    def _resolve_class(self, expression: ast.AST) -> str | None:
        name = ast.unparse(expression)
        if name in self.classes:
            return name
        head, _, tail = name.partition(".")
        imported = self.local_imports.get(head, self.imports.get(head))
        candidate = (
            f"{imported}.{tail}"
            if tail and imported
            else self.local_imports.get(name, self.imports.get(name))
        )
        if candidate in self.classes:
            return candidate
        if not tail:
            scope = self.function_stack[-1] if self.function_stack else None
            resolved = self.resolve_imported_class(self.module, name, scope)
            if resolved:
                return resolved
        candidate = f"{self.module}.{name}"
        return candidate if candidate in self.classes else None

    def _method(self, classname: str, name: str) -> str | None:
        pending = deque([classname])
        seen = set()
        while pending:
            current = pending.popleft()
            if current in seen:
                continue
            seen.add(current)
            candidate = f"{current}.{name}"
            if candidate in self.function_nodes:
                return candidate
            pending.extend(self.bases.get(current, ()))
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(f"{self.module}.{node.name}")
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        prefix = self.class_stack[-1] if self.class_stack else self.module
        function = f"{prefix}.{node.name}"
        if function not in self.function_nodes:
            self.generic_visit(node)
            return
        previous_types = self.local_types
        previous_imports = self.local_imports
        self.local_types = {}
        self.local_imports = {}
        self.function_stack.append(function)
        self.generic_visit(node)
        self.function_stack.pop()
        self.local_types = previous_types
        self.local_imports = previous_imports

    def visit_Import(self, node: ast.Import) -> None:
        if self.function_stack:
            self.local_imports.update(
                _import_bindings(node, self.module, self.is_package)
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.function_stack:
            self.local_imports.update(
                _import_bindings(node, self.module, self.is_package)
            )

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call):
            classname = self._resolve_class(node.value.func)
            if classname:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.local_types[target.id] = classname
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        annotation = node.annotation
        if isinstance(annotation, ast.Subscript):
            annotation = annotation.value
        classname = self._resolve_class(annotation)
        if classname and isinstance(node.target, ast.Name):
            self.local_types[node.target.id] = classname
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not self.function_stack:
            self.generic_visit(node)
            return

        caller = self.function_stack[-1]
        target = node.func
        if isinstance(target, (ast.Name, ast.Attribute)):
            classname = self._resolve_class(target)
            if classname:
                self.dependencies[caller].add(classname)

        if isinstance(target, ast.Attribute):
            receiver = target.value
            method_name = target.attr
            if isinstance(receiver, ast.Name) and receiver.id in {"self", "cls"}:
                if self.class_stack:
                    for child in self.descendants.get(self.class_stack[-1], set()):
                        override = f"{child}.{method_name}"
                        if override in self.function_nodes:
                            self.dependencies[caller].add(override)
            elif isinstance(receiver, ast.Name) and receiver.id in self.local_types:
                method = self._method(self.local_types[receiver.id], method_name)
                if method:
                    self.dependencies[caller].add(method)
            elif isinstance(receiver, ast.Call):
                classname = self._resolve_class(receiver.func)
                method = self._method(classname, method_name) if classname else None
                if method:
                    self.dependencies[caller].add(method)
            else:
                classname = self._resolve_class(receiver)
                if classname:
                    self.dependencies[caller].add(classname)

        self.generic_visit(node)


def get_dynamic_method_dependencies(
    python_files: list[str],
    graph: CallGraphVisitor,
    function_nodes: FunctionNodes,
    resolve_imported_class: Callable[[str, str, str | None], str | None],
) -> dict[str, set[str]]:
    """Add function dependencies that follow known inheritance relationships."""
    module_by_path = {
        os.path.normpath(os.path.abspath(path)): _module_name(module)
        for module, path in graph.module_to_filename.items()
    }
    class_nodes = {
        node.get_name(): node
        for nodes in graph.nodes.values()
        for node in nodes
        if node.flavor == Flavor.CLASS and node.get_name() in function_nodes
    }
    bases = {
        name: {base.get_name() for base in graph.class_base_nodes.get(node, ())}
        for name, node in class_nodes.items()
    }
    descendants: defaultdict[str, set[str]] = defaultdict(set)
    for child, parents in bases.items():
        for parent in parents:
            descendants[parent].add(child)
    for parent in list(descendants):
        pending = list(descendants[parent])
        while pending:
            child = pending.pop()
            for descendant in descendants[child] - descendants[parent]:
                descendants[parent].add(descendant)
                pending.append(descendant)

    methods = {
        classname: {
            name.removeprefix(f"{classname}.")
            for name in function_nodes
            if name.startswith(f"{classname}.")
            and "." not in name.removeprefix(f"{classname}.")
        }
        for classname in class_nodes
    }
    dependencies: defaultdict[str, set[str]] = defaultdict(set)
    for classname, children in descendants.items():
        if children:
            dependencies[classname].update(bases.get(classname, set()))
            dependencies[classname].update(
                f"{classname}.{method}"
                for method in methods.get(classname, set())
                if not method.startswith("_")
            )

    for filepath in python_files:
        module = module_by_path.get(os.path.normpath(os.path.abspath(filepath)))
        if module is None:
            continue
        try:
            with open(filepath, encoding="utf-8") as source:
                tree = ast.parse(source.read(), filename=filepath)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        is_package = os.path.basename(filepath) == "__init__.py"
        module_imports = {}
        for statement in tree.body:
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                module_imports.update(_import_bindings(statement, module, is_package))
        visitor = _DynamicDispatchVisitor(
            module,
            module_imports,
            set(class_nodes),
            bases,
            descendants,
            function_nodes,
            resolve_imported_class,
            is_package,
        )
        visitor.visit(tree)
        for caller, targets in visitor.dependencies.items():
            dependencies[caller].update(targets)

    return dict(dependencies)
