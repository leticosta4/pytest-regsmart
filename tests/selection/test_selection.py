import os
from pathlib import Path

import pytest

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
    filter_pytest_items_for_rtp,
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


@pytest.mark.parametrize(
    ("function_id", "filepath", "expected"),
    [
        ("tests.test_app.test_run", "tests/test_app.py", "tests/test_app.py::test_run"),
        (
            "tests.test_app.TestX.test_x",
            "tests/test_app.py",
            "tests/test_app.py::TestX::test_x",
        ),
        ("tests.test_app.TestX", "tests/test_app.py", "tests/test_app.py::TestX"),
    ],
    ids=["plain function", "class method", "class"],
)
def test_function_id_to_pytest_nodeid(function_id, filepath, expected):
    assert _function_id_to_pytest_nodeid(function_id, filepath) == expected


# ---------------------------------------------------------------------------
# filter_pytest_items_for_rtp (filtering collected items against the selection)
# ---------------------------------------------------------------------------


class _FakeItem:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid


def _select_items(nodeids: list[str], selected_nodes: list[str], level) -> list[str]:
    items = [_FakeItem(nodeid) for nodeid in nodeids]
    filter_pytest_items_for_rtp(items, set(selected_nodes), level)
    return [item.nodeid for item in items]


def test_select_items_function_level_keeps_parameterized_variants():
    nodeids = [
        "test_params.py::test_run_value[10]",
        "test_params.py::test_run_value[20]",
        "test_other.py::test_other_run",
    ]

    selected = _select_items(
        nodeids, ["test_params.py::test_run_value"], DIFF_LEVEL.FUNCTION
    )

    assert selected == [
        "test_params.py::test_run_value[10]",
        "test_params.py::test_run_value[20]",
    ]


def test_select_items_function_level_keeps_methods_of_selected_class():
    nodeids = [
        "test_x.py::TestX::test_a",
        "test_x.py::TestX::test_a[1]",
        "test_other.py::test_other_run",
    ]

    selected = _select_items(nodeids, ["test_x.py::TestX"], DIFF_LEVEL.FUNCTION)

    assert selected == [
        "test_x.py::TestX::test_a",
        "test_x.py::TestX::test_a[1]",
    ]


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
    assert result.full_run is False


# ---------------------------------------------------------------------------
# run_rts (conftest -> full suite)
# ---------------------------------------------------------------------------


def _write_untracked(repo, relpath: str, content: str = "") -> Path:
    filepath = Path(repo.working_tree_dir) / relpath
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    return filepath


def _commit_sample_project_with_conftest(git_repo, commit_file):
    _commit_sample_project(git_repo, commit_file)
    commit_file("conftest.py", "# shared fixtures\n")


@pytest.mark.parametrize("level", [DIFF_LEVEL.FILE, DIFF_LEVEL.FUNCTION])
def test_run_rts_conftest_untracked_triggers_full_run(git_repo, commit_file, monkeypatch, level):
    _commit_sample_project(git_repo, commit_file)
    _write_untracked(git_repo, "conftest.py", "# shared fixtures\n")
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(level)

    assert result.full_run is True
    assert result.affected_tests == []
    assert result.has_diff is True
    assert result.branch == "main"


@pytest.mark.parametrize("level", [DIFF_LEVEL.FILE, DIFF_LEVEL.FUNCTION])
def test_run_rts_conftest_untracked_with_modified_file_triggers_full_run(
    git_repo, commit_file, monkeypatch, level
):
    _commit_sample_project(git_repo, commit_file)
    Path(git_repo.working_tree_dir, "service.py").write_text(
        "def run():\n    return 0\n"
    )
    _write_untracked(git_repo, "conftest.py", "# shared fixtures\n")
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(level)

    assert result.full_run is True
    assert result.affected_tests == []


@pytest.mark.parametrize("level", [DIFF_LEVEL.FILE, DIFF_LEVEL.FUNCTION])
def test_run_rts_conftest_tracked_modified_triggers_full_run(
    git_repo, commit_file, monkeypatch, level
):
    _commit_sample_project_with_conftest(git_repo, commit_file)
    Path(git_repo.working_tree_dir, "conftest.py").write_text(
        "# shared fixtures (edited)\n"
    )
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(level)

    assert result.full_run is True
    assert result.affected_tests == []


@pytest.mark.parametrize("level", [DIFF_LEVEL.FILE, DIFF_LEVEL.FUNCTION])
def test_run_rts_conftest_tracked_deleted_triggers_full_run(
    git_repo, commit_file, monkeypatch, level
):
    _commit_sample_project_with_conftest(git_repo, commit_file)
    os.remove(Path(git_repo.working_tree_dir, "conftest.py"))
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(level)

    assert result.full_run is True
    assert result.affected_tests == []


@pytest.mark.parametrize("level", [DIFF_LEVEL.FILE, DIFF_LEVEL.FUNCTION])
def test_run_rts_conftest_in_subdirectory_untracked_triggers_full_run(
    git_repo, commit_file, monkeypatch, level
):
    _commit_sample_project(git_repo, commit_file)
    _write_untracked(git_repo, "tests/conftest.py", "# shared fixtures\n")
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(level)

    assert result.full_run is True
    assert result.affected_tests == []


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (DIFF_LEVEL.FILE, ["test_app.py"]),
        (DIFF_LEVEL.FUNCTION, ["test_app.py::test_run"]),
    ],
)
def test_run_rts_without_conftest_selects_normally(git_repo, commit_file, monkeypatch, level, expected):
    _commit_sample_project(git_repo, commit_file)
    Path(git_repo.working_tree_dir, "service.py").write_text(
        "def run():\n    return 0\n"
    )
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(level)

    assert result.full_run is False
    assert result.affected_tests == expected


def test_run_rts_conftest_does_not_log_selection_time(git_repo, commit_file, monkeypatch):
    _commit_sample_project(git_repo, commit_file)
    _write_untracked(git_repo, "conftest.py", "# shared fixtures\n")
    monkeypatch.chdir(git_repo.working_tree_dir)
    log_dict: dict = {}

    run_rts(DIFF_LEVEL.FUNCTION, log_dict=log_dict)

    assert "Time to run the regression test selection (s)" not in log_dict


def test_run_rts_without_diff_does_not_log_selection_time(git_repo, commit_file, monkeypatch):
    _commit_sample_project(git_repo, commit_file)
    monkeypatch.chdir(git_repo.working_tree_dir)
    log_dict: dict = {}

    run_rts(DIFF_LEVEL.FUNCTION, log_dict=log_dict)

    assert "Time to run the regression test selection (s)" not in log_dict


def test_run_rts_logs_selection_time_when_selecting(git_repo, commit_file, monkeypatch):
    _commit_sample_project(git_repo, commit_file)
    Path(git_repo.working_tree_dir, "service.py").write_text(
        "def run():\n    return 0\n"
    )
    monkeypatch.chdir(git_repo.working_tree_dir)
    log_dict: dict = {}

    run_rts(DIFF_LEVEL.FUNCTION, log_dict=log_dict)

    assert "Time to run the regression test selection (s)" in log_dict


def test_run_rts_non_python_only_diff_selects_nothing(git_repo, commit_file, monkeypatch):
    _commit_sample_project(git_repo, commit_file)
    Path(git_repo.working_tree_dir, "pyproject.toml").write_text(
        "[project]\nname = \"demo\"\n"
    )
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FILE)

    assert result.has_diff is False
    assert result.affected_tests == []
