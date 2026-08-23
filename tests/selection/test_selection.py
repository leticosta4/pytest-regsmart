from src.pytest_regsmart.selection.deps_graph import (
    DependencyGraph,
    FunctionMetadata,
)
from src.pytest_regsmart.selection.git_manager import DiffResult
from src.pytest_regsmart.selection.selector import (
    _get_affected_tests_at_function_level,
    _get_affected_tests_at_file_level,
)


def test_get_affected_tests_reaches_indirect_test_files_dependents():
    deps_graph = DependencyGraph(
        dependents={
            "service.py": {"ranker.py"},
            "ranker.py": {"main.py"},
            "main.py": {"test_app.py"},
        }
    )
    diff_result = DiffResult(
        modified_files=["service.py"],
        untracked_files=[],
        used_branch="main",
    )

    result = _get_affected_tests_at_file_level(diff_result, deps_graph)

    assert result == ["test_app.py"]


def test_function_level_selection_returns_pytest_nodeids():
    deps_graph = DependencyGraph(
        dependents={"app.service.run": {"tests.test_app.test_run"}},
        function_nodes={
            "app.service.run": FunctionMetadata("app/service.py", 1, 2),
            "tests.test_app.test_run": FunctionMetadata("tests/test_app.py", 3, 4),
        },
        functions_by_file={"app/service.py": {"app.service.run"}},
    )
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(1, 1)]},
    )

    result = _get_affected_tests_at_function_level(diff_result, deps_graph)

    assert result == ["tests/test_app.py::test_run"]
