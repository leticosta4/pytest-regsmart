from __future__ import annotations

from pathlib import Path

from tests.fake_test_data import test_method_one


def _ran_files(out) -> list[str]:
    """Arquivos de teste que apareceram como resultado no run (PASSED/FAILED)."""
    return sorted(
        {
            line.split("::")[0]
            for line in out.outlines
            if "::" in line and ("PASSED" in line or "FAILED" in line)
        }
    )


def _change(repo, filename: str, content: str) -> None:
    (Path(repo.working_tree_dir) / filename).write_text(content)


def test_regsmart_requires_git_repo(pytester):
    pytester.makepyfile(test_method_one=test_method_one)

    out = pytester.runpytest("--regsmart")

    assert any("--regsmart requires a git repository." in x for x in out.errlines)
    assert not any("::" in x and "PASSED" in x for x in out.outlines)


def test_selection_no_rank_only_affected_in_collection_order(selection_project):
    pytester, repo = selection_project
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")

    out = pytester.runpytest("-v", "--regsmart", "--no-rank")

    out.assert_outcomes(passed=3)
    assert _ran_files(out) == ["test_other.py", "test_service.py"]
    assert any("Using --no-rank (RTP disabled)." in x for x in out.outlines)


def test_function_level_selection_keeps_only_affected_test_functions(
        selection_project):
    pytester, repo = selection_project
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")

    out = pytester.runpytest(
        "-v", "--regsmart", "--diff-level=function", "--no-rank"
    )

    out.assert_outcomes(passed=3)
    assert _ran_files(out) == ["test_other.py", "test_service.py"]


def test_function_level_selection_can_be_ranked(selection_project):
    pytester, repo = selection_project
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")

    out = pytester.runpytest("-v", "--regsmart", "--diff-level=function")

    out.assert_outcomes(passed=3)
    assert _ran_files(out) == ["test_other.py", "test_service.py"]


def test_selection_with_rank_levels(selection_project):
    pytester, repo = selection_project
    pytester.runpytest("-v")
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")

    for level in ("put", "function", "module"):
        out = pytester.runpytest("-v", "--regsmart", f"--rank-level={level}")

        out.assert_outcomes(passed=3)
        assert _ran_files(out) == ["test_other.py", "test_service.py"]


def test_selection_with_replay_order(selection_project):
    pytester, repo = selection_project
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")
    pytester.maketxtfile(
        replay_order="""
        test_other.py::test_other_run
        test_service.py::test_service_fast
        test_service.py::test_service_slow
        """
    )

    out = pytester.runpytest("-v", "--regsmart", "--rank-replay=replay_order.txt")

    out.assert_outcomes(passed=3)
    test_lines = [x for x in out.outlines if "::" in x and "PASSED" in x]
    assert test_lines[0] == "test_other.py::test_other_run PASSED"


def test_selection_with_random_model(selection_project):
    pytester, repo = selection_project
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")

    out = pytester.runpytest(
        "-v", "--regsmart", "--rank-weight=0-0", "--rank-seed=42"
    )

    out.assert_outcomes(passed=3)
    assert _ran_files(out) == ["test_other.py", "test_service.py"]


def test_seed_fix_change_test_file_selects_only_it(selection_project):
    pytester, repo = selection_project
    _change(repo, "test_service.py", "from service import run\n\n"
            "def test_service_fast():\n    assert run() == 42\n")

    out = pytester.runpytest("-v", "--regsmart", "--no-rank")

    out.assert_outcomes(passed=1)
    assert _ran_files(out) == ["test_service.py"]


def test_no_diff_with_rank_runs_everything(selection_project):
    pytester, _repo = selection_project

    out = pytester.runpytest("-v", "--regsmart")

    out.assert_outcomes(passed=4)
    assert any(
        "No diff detected: regression test selection was skipped." in x
        for x in out.outlines
    )
    assert any("Time to run the regression test selection (s)" in x for x in out.outlines)


def test_no_diff_with_no_rank_plugin_does_nothing(selection_project):
    pytester, _repo = selection_project

    out = pytester.runpytest("-v", "--regsmart", "--no-rank")

    out.assert_outcomes(passed=4)
    assert any(
        "No diff detected and --no-rank enabled: pytest-regsmart is not doing anything."
        in x for x in out.outlines
    )
