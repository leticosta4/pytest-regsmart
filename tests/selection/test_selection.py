from pytest_regsmart.selection.git_manager import DiffResult
from pytest_regsmart.selection.deps_graph import DependencyGraph
from pytest_regsmart.selection.selector import get_affected_tests


def test_get_affected_tests_reaches_indirect_test_dependents():
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
    )

    result = get_affected_tests(diff_result, deps_graph)

    assert result == ["test_app.py"]
