import os
from pathlib import Path

import pytest

from src.pytest_regsmart.const import DEFAULT_DIFF_LEVEL, DIFF_LEVEL, DIFF_SOURCE
from src.pytest_regsmart.selection import selector as selector_module
from src.pytest_regsmart.selection.models import (
    DependencyGraph,
    DiffResult,
    FunctionMetadata,
)
from src.pytest_regsmart.selection.selector import (
    SELECTION_TIME_KEY,
    SELECTION_TIME_KEY_FILE_LEVEL,
    SelectionResult,
    _add_collected_fixture_edges,
    _function_id_to_pytest_nodeid,
    _get_affected_tests_at_file_level,
    _get_affected_tests_at_function_level,
    _unresolved_changed_files,
    filter_pytest_items_for_rtp,
    line_diff_match_function_ids,
    run_rts,
    run_rts_with_fallback,
)

WORKTREE = DIFF_SOURCE.WORKTREE
COMMIT = DIFF_SOURCE.COMMIT


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


def test_collected_fixture_closure_links_fixture_to_test(tmp_path, monkeypatch):
    fixture_path = tmp_path / "conftest.py"
    fixture_path.write_text("def settings():\n    return object()\n")
    test_path = tmp_path / "test_settings.py"
    test_path.write_text("def test_assign(settings):\n    settings.value = 1\n")
    monkeypatch.chdir(tmp_path)

    class FixtureDef:
        func = __import__("runpy").run_path(str(fixture_path))["settings"]

    class FixtureInfo:
        def __init__(self):
            self.name2fixturedefs = {"settings": [FixtureDef()]}

    class Item:
        path = test_path
        nodeid = "test_settings.py::test_assign"
        def __init__(self):
            self._fixtureinfo = FixtureInfo()

    graph = DependencyGraph(
        dependents={},
        function_nodes={
            "conftest.settings": FunctionMetadata("conftest.py", 1, 2),
            "test_settings.test_assign": FunctionMetadata("test_settings.py", 1, 2),
        },
    )

    _add_collected_fixture_edges([Item()], graph)

    assert graph.dependents["conftest.settings"] == {"test_settings.test_assign"}


def test_function_level_selection_keeps_tests_that_run_nested_pytest():
    deps_graph = DependencyGraph(
        dependents={},
        function_nodes={
            "app.service.run": FunctionMetadata("app/service.py", 1, 2),
            "tests.test_nested.TestIntegration.test_child": FunctionMetadata(
                "tests/test_nested.py", 3, 5
            ),
        },
        functions_by_file={"app/service.py": {"app.service.run"}},
        subprocess_tests={"tests.test_nested.TestIntegration.test_child"},
    )
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(1, 1)]},
    )

    result = _get_affected_tests_at_function_level(diff_result, deps_graph)

    assert result == ["tests/test_nested.py::TestIntegration::test_child"]


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
# _unresolved_changed_files
# ---------------------------------------------------------------------------


def test_unresolved_hunk_outside_any_function():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(1, 1)]},
    )

    assert _unresolved_changed_files(diff_result, deps_graph) == {"app/service.py"}


def test_unresolved_deleted_function_anchor_outside_surviving_functions():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(5, 5)]},
    )

    assert _unresolved_changed_files(diff_result, deps_graph) == {"app/service.py"}


def test_pure_deletion_hunk_is_unresolved_even_when_anchor_hits_surviving_class():
    deps_graph = DependencyGraph(
        dependents={},
        function_nodes={"app.service.Calc": FunctionMetadata("app/service.py", 1, 20)},
        functions_by_file={"app/service.py": {"app.service.Calc"}},
    )
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(17, 17)]},
        pure_deletion_files={"app/service.py"},
    )

    assert _unresolved_changed_files(diff_result, deps_graph) == {"app/service.py"}


def test_unresolved_file_absent_from_graph():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["deleted/service.py"],
        used_branch="main",
    )

    assert _unresolved_changed_files(diff_result, deps_graph) == {"deleted/service.py"}


def test_resolved_hunk_inside_function():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=["app/service.py"],
        used_branch="main",
        changed_line_ranges={"app/service.py": [(6, 7)]},
    )

    assert _unresolved_changed_files(diff_result, deps_graph) == set()


def test_untracked_file_with_functions_is_resolved():
    deps_graph = _function_graph()
    diff_result = DiffResult(
        modified_files=[],
        untracked_files=["app/new.py"],
        used_branch="main",
    )

    assert _unresolved_changed_files(diff_result, deps_graph) == set()


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


def test_select_items_function_level_matches_only_at_nodeid_boundaries():
    nodeids = [
        "test_x.py::test_a",
        "test_x.py::test_ab",
        "test_x.py::test_a_b[1]",
        "test_x.py::TestA::test_m",
        "test_x.py::TestAB::test_m",
    ]

    selected = _select_items(
        nodeids, ["test_x.py::test_a", "test_x.py::TestA"], DIFF_LEVEL.FUNCTION
    )

    assert selected == ["test_x.py::test_a", "test_x.py::TestA::test_m"]


def test_select_items_function_level_handles_separators_inside_param_ids():
    nodeids = [
        "test_p.py::test_run[a::b]",
        "test_p.py::test_run[x[1]]",
        "test_p.py::TestC::test_m[c::d]",
        "test_p.py::test_other[test_run]",
    ]

    selected = _select_items(
        nodeids, ["test_p.py::test_run", "test_p.py::TestC::test_m"], DIFF_LEVEL.FUNCTION
    )

    assert selected == [
        "test_p.py::test_run[a::b]",
        "test_p.py::test_run[x[1]]",
        "test_p.py::TestC::test_m[c::d]",
    ]


def test_select_items_function_level_keeps_collection_order():
    nodeids = ["test_b.py::test_2", "test_a.py::test_1", "test_b.py::test_1"]

    selected = _select_items(
        nodeids, ["test_b.py::test_1", "test_b.py::test_2"], DIFF_LEVEL.FUNCTION
    )

    assert selected == ["test_b.py::test_2", "test_b.py::test_1"]


def _reference_function_level_filter(nodeids: list[str], selected_nodes: set[str]):
    """The previous O(items x selected) implementation, kept as an oracle."""
    return [
        nodeid
        for nodeid in nodeids
        if any(
            nodeid == node or nodeid.startswith((f"{node}[", f"{node}::"))
            for node in selected_nodes
        )
    ]


def test_select_items_function_level_is_equivalent_to_previous_filter():
    import random

    rng = random.Random(0)
    parts = ["test_a.py", "test_ab.py", "TestX", "TestXY", "test_m", "test_mn", "f"]
    params = ["", "[1]", "[a::b]", "[x[0]]", "[]", "[test_m]"]

    def nodeid():
        depth = rng.randint(1, 3)
        return "::".join(rng.choice(parts) for _ in range(depth + 1)) + rng.choice(params)

    nodeids = [nodeid() for _ in range(400)]
    selected_nodes = {
        nid.split("[")[0].rsplit("::", rng.randint(0, 1))[0]
        for nid in rng.sample(nodeids, 60)
    } | {nodeid() for _ in range(20)}

    assert _select_items(nodeids, list(selected_nodes), DIFF_LEVEL.FUNCTION) == (
        _reference_function_level_filter(nodeids, selected_nodes)
    )


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


def _edit_worktree(git_repo, filename: str, content: str) -> None:
    Path(git_repo.working_tree_dir, filename).write_text(content)


def test_run_rts_function_level_returns_full_nodeids(
    git_repo, commit_file, monkeypatch
):
    _commit_sample_project(git_repo, commit_file)
    _edit_worktree(git_repo, "service.py", "def run():\n    return 0\n")
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FUNCTION, diff_source=WORKTREE)

    assert result.affected_tests == ["test_app.py::test_run"]
    assert result.has_diff is True
    assert result.branch == "main"


def test_run_rts_function_level_selects_tests_parametrized_with_changed_function(
    git_repo, commit_file, monkeypatch
):
    commit_file(
        "service.py",
        "def run():\n    return 42\n\ndef other():\n    return 1\n",
    )
    commit_file(
        "test_app.py",
        "import pytest\n"
        "import service\n"
        "\n"
        "FUNCS = {'run': service.run}\n"
        "PARAMS = [pytest.param(func, id=key) for key, func in FUNCS.items()]\n"
        "\n"
        "@pytest.mark.parametrize('func', PARAMS)\n"
        "def test_parametrized(func):\n"
        "    assert func()\n"
        "\n"
        "def test_other():\n"
        "    assert service.other()\n",
    )
    git_repo.git.branch("-m", "main")
    _edit_worktree(
        git_repo, "service.py", "def run():\n    return 0\n\ndef other():\n    return 1\n"
    )
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FUNCTION, diff_source=WORKTREE)

    assert result.affected_tests == ["test_app.py::test_parametrized"]


def test_run_rts_commit_source_selects_committed_change(
    git_repo, commit_file, monkeypatch
):
    _commit_sample_project(git_repo, commit_file)
    git_repo.git.checkout("-b", "feature")
    _edit_worktree(git_repo, "service.py", "def run():\n    return 0\n")
    git_repo.index.add("service.py")
    git_repo.index.commit("mutate service")
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FUNCTION, diff_source=COMMIT)

    assert result.affected_tests == ["test_app.py::test_run"]
    assert result.has_diff is True
    assert result.branch == "main"


def test_run_rts_commit_source_ignores_worktree_conftest(
    git_repo, commit_file, monkeypatch
):
    _commit_sample_project(git_repo, commit_file)
    _edit_worktree(git_repo, "service.py", "def run():\n    return 0\n")
    _write_untracked(git_repo, "conftest.py", "# rewritten by CI\n")
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FUNCTION, diff_source=COMMIT)

    assert result.full_run is False
    assert result.has_diff is False
    assert result.affected_tests == []


def test_run_rts_function_level_reports_unresolved_files(
    git_repo, commit_file, monkeypatch
):
    _commit_sample_project(git_repo, commit_file)
    commit_file("const_mod.py", "VALUE = 1\n")
    Path(git_repo.working_tree_dir, "const_mod.py").write_text("VALUE = 2\n")
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FUNCTION, diff_source=WORKTREE)

    assert result.affected_tests == []
    assert result.unresolved_files == ["const_mod.py"]


def test_run_rts_function_level_resolved_diff_has_no_unresolved_files(
    git_repo, commit_file, monkeypatch
):
    _commit_sample_project(git_repo, commit_file)
    Path(git_repo.working_tree_dir, "service.py").write_text(
        "def run():\n    return 0\n"
    )
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(DIFF_LEVEL.FUNCTION, diff_source=WORKTREE)

    assert result.affected_tests == ["test_app.py::test_run"]
    assert result.unresolved_files == []


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

    result = run_rts(level, diff_source=WORKTREE)

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

    result = run_rts(level, diff_source=WORKTREE)

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

    result = run_rts(level, diff_source=WORKTREE)

    assert result.full_run is True
    assert result.affected_tests == []


@pytest.mark.parametrize("level", [DIFF_LEVEL.FILE, DIFF_LEVEL.FUNCTION])
def test_run_rts_conftest_tracked_deleted_triggers_full_run(
    git_repo, commit_file, monkeypatch, level
):
    _commit_sample_project_with_conftest(git_repo, commit_file)
    os.remove(Path(git_repo.working_tree_dir, "conftest.py"))
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(level, diff_source=WORKTREE)

    assert result.full_run is True
    assert result.affected_tests == []


@pytest.mark.parametrize("level", [DIFF_LEVEL.FILE, DIFF_LEVEL.FUNCTION])
def test_run_rts_conftest_in_subdirectory_untracked_triggers_full_run(
    git_repo, commit_file, monkeypatch, level
):
    _commit_sample_project(git_repo, commit_file)
    _write_untracked(git_repo, "tests/conftest.py", "# shared fixtures\n")
    monkeypatch.chdir(git_repo.working_tree_dir)

    result = run_rts(level, diff_source=WORKTREE)

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

    result = run_rts(level, diff_source=WORKTREE)

    assert result.full_run is False
    assert result.affected_tests == expected


def test_run_rts_conftest_does_not_log_selection_time(git_repo, commit_file, monkeypatch):
    _commit_sample_project(git_repo, commit_file)
    _write_untracked(git_repo, "conftest.py", "# shared fixtures\n")
    monkeypatch.chdir(git_repo.working_tree_dir)
    log_dict: dict = {}

    run_rts(DIFF_LEVEL.FUNCTION, log_dict=log_dict, diff_source=WORKTREE)

    assert "Time to run the regression test selection (s)" not in log_dict


def test_run_rts_without_diff_does_not_log_selection_time(git_repo, commit_file, monkeypatch):
    _commit_sample_project(git_repo, commit_file)
    monkeypatch.chdir(git_repo.working_tree_dir)
    log_dict: dict = {}

    run_rts(DIFF_LEVEL.FUNCTION, log_dict=log_dict, diff_source=WORKTREE)

    assert "Time to run the regression test selection (s)" not in log_dict


def test_run_rts_logs_selection_time_when_selecting(git_repo, commit_file, monkeypatch):
    _commit_sample_project(git_repo, commit_file)
    Path(git_repo.working_tree_dir, "service.py").write_text(
        "def run():\n    return 0\n"
    )
    monkeypatch.chdir(git_repo.working_tree_dir)
    log_dict: dict = {}

    run_rts(DIFF_LEVEL.FUNCTION, log_dict=log_dict, diff_source=WORKTREE)

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


# ---------------------------------------------------------------------------
# run_rts_with_fallback (function -> file cascade)
# ---------------------------------------------------------------------------


def _fake_rts(monkeypatch, results_by_level: dict[DIFF_LEVEL, SelectionResult]):
    calls: list[tuple[DIFF_LEVEL, str]] = []

    def fake(
        level=DEFAULT_DIFF_LEVEL,
        log_dict=None,
        time_key=SELECTION_TIME_KEY,
        diff_source=None,
        files_to_select=None,
    ):
        calls.append((level, time_key))
        if log_dict is not None:
            log_dict[time_key] = 1.0
        return results_by_level[level]

    monkeypatch.setattr(selector_module, "run_rts", fake)
    return calls


def _result(level: DIFF_LEVEL, affected: list[str], **kwargs) -> SelectionResult:
    return SelectionResult(
        affected_tests=affected,
        has_diff=True,
        branch="main",
        level=level,
        **kwargs,
    )


def test_fallback_degrades_to_file_level_when_function_selection_is_empty(monkeypatch):
    calls = _fake_rts(
        monkeypatch,
        {
            DIFF_LEVEL.FUNCTION: _result(DIFF_LEVEL.FUNCTION, []),
            DIFF_LEVEL.FILE: _result(DIFF_LEVEL.FILE, ["tests/test_core.py"]),
        },
    )
    log_dict: dict = {}

    result = run_rts_with_fallback(level=DIFF_LEVEL.FUNCTION, log_dict=log_dict)

    assert result.affected_tests == ["tests/test_core.py"]
    assert result.level == DIFF_LEVEL.FILE
    assert result.degraded_to_file is True
    assert [level for level, _ in calls] == [DIFF_LEVEL.FUNCTION, DIFF_LEVEL.FILE]
    assert calls[1][1] == SELECTION_TIME_KEY_FILE_LEVEL
    assert SELECTION_TIME_KEY in log_dict
    assert SELECTION_TIME_KEY_FILE_LEVEL in log_dict


def test_fallback_with_both_levels_empty_returns_empty_result(monkeypatch):
    _fake_rts(
        monkeypatch,
        {
            DIFF_LEVEL.FUNCTION: _result(DIFF_LEVEL.FUNCTION, []),
            DIFF_LEVEL.FILE: _result(DIFF_LEVEL.FILE, []),
        },
    )

    result = run_rts_with_fallback(level=DIFF_LEVEL.FUNCTION)

    assert result.affected_tests == []
    assert result.degraded_to_file is True
    assert result.level == DIFF_LEVEL.FILE


def test_fallback_supplements_nonempty_function_selection_for_unresolved_files(monkeypatch):
    calls = []

    def fake(
        level=DEFAULT_DIFF_LEVEL,
        log_dict=None,
        time_key=SELECTION_TIME_KEY,
        diff_source=None,
        files_to_select=None,
    ):
        calls.append((level, time_key, files_to_select))
        if level == DIFF_LEVEL.FUNCTION:
            return _result(
                level,
                ["test_a.py::test_one"],
                unresolved_files=["const_mod.py"],
            )
        return _result(level, ["test_b.py"])

    monkeypatch.setattr(selector_module, "run_rts", fake)

    result = run_rts_with_fallback(level=DIFF_LEVEL.FUNCTION)

    assert result.affected_tests == ["test_a.py::test_one", "test_b.py"]
    assert result.level == DIFF_LEVEL.FUNCTION
    assert result.degraded_to_file is True
    assert result.degraded_from_unresolved is True
    assert result.unresolved_files == ["const_mod.py"]
    assert [level for level, _, _ in calls] == [DIFF_LEVEL.FUNCTION, DIFF_LEVEL.FILE]
    assert calls[1][2] == {"const_mod.py"}


def test_fallback_not_triggered_when_function_selection_finds_tests(monkeypatch):
    calls = _fake_rts(
        monkeypatch,
        {DIFF_LEVEL.FUNCTION: _result(DIFF_LEVEL.FUNCTION, ["test_a.py::test_one"])},
    )

    result = run_rts_with_fallback(level=DIFF_LEVEL.FUNCTION)

    assert result.affected_tests == ["test_a.py::test_one"]
    assert result.level == DIFF_LEVEL.FUNCTION
    assert result.degraded_to_file is False
    assert [level for level, _ in calls] == [DIFF_LEVEL.FUNCTION]


def test_fallback_not_triggered_when_level_is_file(monkeypatch):
    calls = _fake_rts(monkeypatch, {DIFF_LEVEL.FILE: _result(DIFF_LEVEL.FILE, [])})

    result = run_rts_with_fallback(level=DIFF_LEVEL.FILE)

    assert result.affected_tests == []
    assert result.degraded_to_file is False
    assert [level for level, _ in calls] == [DIFF_LEVEL.FILE]


@pytest.mark.parametrize(
    "result",
    [
        SelectionResult(
            affected_tests=[],
            has_diff=True,
            branch="main",
            full_run=True,
            level=DIFF_LEVEL.FUNCTION,
        ),
        SelectionResult(
            affected_tests=[],
            has_diff=True,
            branch="main",
            no_merge_base=True,
            level=DIFF_LEVEL.FUNCTION,
        ),
        SelectionResult(
            affected_tests=[], has_diff=False, branch="main", level=DIFF_LEVEL.FUNCTION
        ),
    ],
    ids=["full_run", "no_merge_base", "no_diff"],
)
def test_fallback_not_triggered_for_safe_degradation_guards(monkeypatch, result):
    calls = _fake_rts(monkeypatch, {DIFF_LEVEL.FUNCTION: result})

    returned = run_rts_with_fallback(level=DIFF_LEVEL.FUNCTION)

    assert returned is result
    assert returned.degraded_to_file is False
    assert [level for level, _ in calls] == [DIFF_LEVEL.FUNCTION]


def test_fallback_forwards_diff_source_to_selection(monkeypatch):
    """The diff source must reach the real selection, including on the fallback."""
    seen: list = []

    def fake(
        level=DEFAULT_DIFF_LEVEL, log_dict=None, time_key=SELECTION_TIME_KEY, diff_source=None
    ):
        seen.append(diff_source)
        return _result(level, ["test_a.py::test_one"])

    monkeypatch.setattr(selector_module, "run_rts", fake)

    run_rts_with_fallback(level=DIFF_LEVEL.FUNCTION, diff_source=WORKTREE)

    assert seen == [WORKTREE]


def _add_collected_fixture_edges_oracle(items, deps_graph):
    """Implementation before the per-name index, kept as an oracle."""
    import os

    by_location = {}
    for function_id, metadata in deps_graph.function_nodes.items():
        by_location.setdefault(
            (os.path.normpath(metadata.filepath), function_id.rsplit(".", 1)[-1]), set()
        ).add(function_id)
    for item in items:
        test_path = os.path.normpath(str(item.path))
        test_name = item.nodeid.split("::")[-1].split("[")[0]
        test_ids = by_location.get((test_path, test_name), set())
        if not test_ids:
            test_ids = {
                fid for fid, metadata in deps_graph.function_nodes.items()
                if metadata.filepath.endswith(test_path.replace(os.sep, "/").split("/")[-1])
                and fid.rsplit(".", 1)[-1] == test_name
            }
        if not test_ids:
            continue
        definitions = getattr(item._fixtureinfo, "name2fixturedefs", {}) or {}
        fixture_functions = set()
        for fixturedefs in definitions.values():
            for fixturedef in fixturedefs or ():
                func = fixturedef.func
                fixture_path = os.path.relpath(func.__code__.co_filename, os.getcwd())
                fixture_functions.update(
                    by_location.get((os.path.normpath(fixture_path), func.__name__), ())
                )
        for fixture_id in fixture_functions:
            deps_graph.dependents.setdefault(fixture_id, set()).update(test_ids)


def test_collected_fixture_edges_match_previous_implementation(tmp_path, monkeypatch):
    import copy
    import runpy

    (tmp_path / "tests" / "unit").mkdir(parents=True)
    conftest = tmp_path / "tests" / "conftest.py"
    conftest.write_text(
        "def db():\n    return 1\n\n\ndef settings():\n    return 2\n\n\ndef cache():\n    return 3\n"
    )
    monkeypatch.chdir(tmp_path)
    fixtures = runpy.run_path(str(conftest))

    class FixtureDef:
        def __init__(self, name):
            self.func = fixtures[name]

    class FixtureInfo:
        def __init__(self, names):
            self.name2fixturedefs = {name: [FixtureDef(name)] for name in names}

    class Item:
        def __init__(self, relpath, nodeid_tail, fixture_names):
            # pytest gives absolute paths; graph paths are relative to the repo
            self.path = tmp_path / relpath
            self.nodeid = f"{relpath}::{nodeid_tail}"
            self._fixtureinfo = FixtureInfo(fixture_names)

    function_nodes = {
        "tests.conftest.db": FunctionMetadata("tests/conftest.py", 1, 2),
        "tests.conftest.settings": FunctionMetadata("tests/conftest.py", 5, 6),
        "tests.conftest.cache": FunctionMetadata("tests/conftest.py", 9, 10),
        "tests.test_api.test_get": FunctionMetadata("tests/test_api.py", 1, 2),
        "tests.test_api.TestPost.test_create": FunctionMetadata("tests/test_api.py", 4, 6),
        "tests.unit.test_api.test_get": FunctionMetadata("tests/unit/test_api.py", 1, 2),
        "tests.unit.test_models.test_save": FunctionMetadata("tests/unit/test_models.py", 1, 2),
        "tests.unit.test_models.TestModel.test_save": FunctionMetadata(
            "tests/unit/test_models.py", 4, 6
        ),
    }
    items = [
        Item("tests/test_api.py", "test_get[a]", ["db"]),
        Item("tests/test_api.py", "test_get[b]", ["db", "settings"]),
        Item("tests/test_api.py", "TestPost::test_create", ["settings"]),
        Item("tests/unit/test_api.py", "test_get", ["cache"]),
        Item("tests/unit/test_models.py", "test_save[x-1]", ["db", "cache"]),
        Item("tests/unit/test_models.py", "TestModel::test_save", ["settings"]),
        Item("tests/unit/test_models.py", "test_missing", ["db"]),
    ]
    graph = DependencyGraph(dependents={"tests.conftest.db": {"x.y"}}, function_nodes=function_nodes)
    expected = copy.deepcopy(graph)

    _add_collected_fixture_edges(items, graph)
    _add_collected_fixture_edges_oracle(items, expected)

    assert graph.dependents == expected.dependents
    assert graph.dependents["tests.conftest.db"] >= {"x.y", "tests.test_api.test_get"}
