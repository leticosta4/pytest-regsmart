from pathlib import Path

from src.pytest_regsmart.const import DIFF_LEVEL
from src.pytest_regsmart.selection.deps_graph import (
    DependencyGraph,
    FunctionMetadata,
)
from src.pytest_regsmart.selection.git_manager import DiffResult
from src.pytest_regsmart.selection.selector import (
    _function_id_to_pytest_nodeid,
    _get_affected_tests_at_file_level,
    _get_affected_tests_at_function_level,
    line_diff_match_function_ids,
    run_rts,
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


# ---------------------------------------------------------------------------
# line_diff_match_function_ids
# ---------------------------------------------------------------------------


def _function_graph() -> DependencyGraph:
    return DependencyGraph(
        dependents={
            "app.service.run": {"tests.test_app.test_run"},
            "app.service.helper": {"tests.test_app.test_helper"},
            "app.new.fresh": set(),
        },
        function_nodes={
            "app.service.run": FunctionMetadata("app/service.py", 3, 4),
            "app.service.helper": FunctionMetadata("app/service.py", 6, 7),
            "app.new.fresh": FunctionMetadata("app/new.py", 1, 2),
            "tests.test_app.test_run": FunctionMetadata("tests/test_app.py", 3, 4),
            "tests.test_app.test_helper": FunctionMetadata("tests/test_app.py", 6, 7),
        },
        functions_by_file={
            "app/service.py": {"app.service.run", "app.service.helper"},
            "app/new.py": {"app.new.fresh"},
            "tests/test_app.py": {
                "tests.test_app.test_run",
                "tests.test_app.test_helper",
            },
        },
    )


def test_line_diff_matches_only_touched_function():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(6, 7)]},
    )

    changed = line_diff_match_function_ids(diff_result, deps_graph)

    assert changed == {"app.service.helper"}


def test_line_diff_spanning_functions_matches_all_of_them():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(3, 7)]},
    )

    changed = line_diff_match_function_ids(diff_result, deps_graph)

    assert changed == {"app.service.run", "app.service.helper"}


def test_line_diff_outside_any_function_falls_back_to_whole_file():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(1, 1)]},
    )

    changed = line_diff_match_function_ids(diff_result, deps_graph)

    assert changed == {"app.service.run", "app.service.helper"}


def test_line_diff_modified_file_without_ranges_uses_whole_file():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
    )

    changed = line_diff_match_function_ids(diff_result, deps_graph)

    assert changed == {"app.service.run", "app.service.helper"}


def test_line_diff_untracked_file_marks_all_its_functions():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=[],
        untracked_files=["app/new.py"],
        used_branch="main",
    )

    changed = line_diff_match_function_ids(diff_result, deps_graph)

    assert changed == {"app.new.fresh"}


def test_line_diff_file_absent_from_graph_contributes_nothing():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["deleted/service.py"],
        used_branch="main",
    )

    changed = line_diff_match_function_ids(diff_result, deps_graph)

    assert changed == set()


# ---------------------------------------------------------------------------
# _function_id_to_pytest_nodeid
# ---------------------------------------------------------------------------


def test_nodeid_conversion_for_plain_function():
    nodeid = _function_id_to_pytest_nodeid(
        "tests.test_app.test_run", "tests/test_app.py"
    )

    assert nodeid == "tests/test_app.py::test_run"


def test_nodeid_conversion_for_class_method():
    nodeid = _function_id_to_pytest_nodeid(
        "pkg.mod.Calculator.add", "pkg/mod.py"
    )

    assert nodeid == "pkg/mod.py::Calculator::add"


# ---------------------------------------------------------------------------
# run_rts (end-to-end on a real repo)
# ---------------------------------------------------------------------------


def _commit_sample_project(git_repo, commit_file):
    commit_file("service.py", "def run():\n    return 42\n")
    commit_file(
        "test_app.py",
        "from service import run\n"
        "\n"
        "def test_run():\n"
        "    assert run()\n",
    )
    git_repo.git.branch("-m", "main")


def test_run_rts_function_level_returns_full_nodeids(
    git_repo, commit_file, monkeypatch
):
    _commit_sample_project(git_repo, commit_file)
    Path(git_repo.working_tree_dir, "service.py").write_text(
        "def run():\n    return 0\n"
    )
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FUNCTION)

    assert result.affected_tests == ["test_app.py::test_run"]
    assert result.has_diff is True
    assert result.branch == "main"


def test_run_rts_without_diff_selects_nothing(git_repo, commit_file, monkeypatch):
    _commit_sample_project(git_repo, commit_file)
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FUNCTION)

    assert result.affected_tests == []
    assert result.has_diff is False
    assert result.branch == "main"
