"""Static discovery of tests that launch a nested pytest run."""

from __future__ import annotations

import ast
import os

from .models import FunctionNodes

_PYTESTER_RUN_METHODS = {"runpytest_subprocess", "runpytest"}


class _NestedPytestVisitor(ast.NodeVisitor):
    def __init__(self, module_name: str, function_nodes: FunctionNodes) -> None:
        self.module_name = module_name
        self.function_nodes = function_nodes
        self.classes: list[str] = []
        self.functions: list[str] = []
        self.tests: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        method = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if method in _PYTESTER_RUN_METHODS and self.functions:
            prefix = ".".join([self.module_name, *self.classes])
            function_id = f"{prefix}.{self.functions[-1]}"
            if function_id in self.function_nodes:
                self.tests.add(function_id)
        self.generic_visit(node)


def find_nested_pytest_tests(
    python_files: list[str],
    module_to_filename: dict[str, str],
    function_nodes: FunctionNodes,
) -> set[str]:
    """Return function ids containing calls to pytester's nested-run helpers."""
    modules_by_path = {
        os.path.normpath(path): module for module, path in module_to_filename.items()
    }
    tests: set[str] = set()

    for filepath in python_files:
        module_name = modules_by_path.get(os.path.normpath(filepath))
        if module_name is None:
            continue
        try:
            with open(filepath, encoding="utf-8") as source:
                tree = ast.parse(source.read(), filename=filepath)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        visitor = _NestedPytestVisitor(module_name, function_nodes)
        visitor.visit(tree)
        tests.update(visitor.tests)

    return tests
