from __future__ import annotations

from pathlib import Path

from tests.fake_test_data import test_method_one


def _ran_files(out) -> list[str]:
    return sorted(
        {
            line.split("::")[0]
            for line in out.outlines
            if "::" in line and ("PASSED" in line or "FAILED" in line)
        }
    )


def _ran_nodeids(out) -> list[str]:
    return sorted(
        line.split(" ")[0]
        for line in out.outlines
        if "::" in line and "PASSED" in line
    )


def _change(repo, filename: str, content: str) -> None:
    (Path(repo.working_tree_dir) / filename).write_text(content)


def _commit_new_file(repo, filename: str, content: str) -> None:
    (Path(repo.working_tree_dir) / filename).write_text(content)
    repo.index.add([filename])
    repo.index.commit(f"Add {filename}")


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


def test_function_level_selects_only_tests_of_changed_function(selection_project):
    pytester, repo = selection_project
    _commit_new_file(
        repo,
        "extra.py",
        'def alpha():\n    return "a"\n\n\ndef beta():\n    return "b"\n',
    )
    _commit_new_file(
        repo,
        "test_extra.py",
        "from extra import alpha, beta\n"
        "\n"
        'def test_alpha():\n    assert alpha() == "a"\n'
        "\n"
        'def test_beta():\n    assert beta() == "b"\n',
    )
    _change(
        repo,
        "extra.py",
        'def alpha():\n    return "a"\n\n\ndef beta():\n    return "b"  # touched\n',
    )

    out = pytester.runpytest("-v", "--regsmart", "--diff-level=function", "--no-rank")

    out.assert_outcomes(passed=1)
    assert _ran_nodeids(out) == ["test_extra.py::test_beta"]


def test_function_level_runs_parametrized_variants_of_selected_node(selection_project):
    pytester, repo = selection_project
    _commit_new_file(
        repo,
        "test_params.py",
        "import pytest\n"
        "from service import run\n"
        "\n"
        '@pytest.mark.parametrize("value", [10, 20])\n'
        "def test_run_value(value):\n"
        "    assert run() == 42\n",
    )
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")

    out = pytester.runpytest("-v", "--regsmart", "--diff-level=function", "--no-rank")

    out.assert_outcomes(passed=5)
    nodeids = _ran_nodeids(out)
    assert "test_params.py::test_run_value[10]" in nodeids
    assert "test_params.py::test_run_value[20]" in nodeids


def test_diff_level_ini_option_used_when_cli_absent(selection_project):
    pytester, repo = selection_project
    _commit_new_file(
        repo,
        "extra.py",
        'def alpha():\n    return "a"\n\n\ndef beta():\n    return "b"\n',
    )
    _commit_new_file(
        repo,
        "test_extra.py",
        "from extra import alpha, beta\n"
        "\n"
        'def test_alpha():\n    assert alpha() == "a"\n'
        "\n"
        'def test_beta():\n    assert beta() == "b"\n',
    )
    _change(
        repo,
        "extra.py",
        'def alpha():\n    return "a"\n\n\ndef beta():\n    return "b"  # touched\n',
    )
    (Path(repo.working_tree_dir) / "pytest.ini").write_text(
        "[pytest]\nconsole_output_style = classic\ndiff_level = file\n"
    )

    out = pytester.runpytest("-v", "--regsmart", "--no-rank")

    out.assert_outcomes(passed=2)
    assert _ran_files(out) == ["test_extra.py"]


def test_invalid_rank_weight_ini_raises_usage_error(selection_project):
    pytester, repo = selection_project
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")
    (Path(repo.working_tree_dir) / "pytest.ini").write_text(
        "[pytest]\nconsole_output_style = classic\nrank_weight = 1-3-2\n"
    )

    out = pytester.runpytest("-v", "--regsmart")

    assert any("rank_weight" in x for x in out.errlines)
    assert not any("::" in x and "PASSED" in x for x in out.outlines)


def test_invalid_diff_level_ini_raises_usage_error(selection_project):
    pytester, repo = selection_project
    (Path(repo.working_tree_dir) / "pytest.ini").write_text(
        "[pytest]\nconsole_output_style = classic\ndiff_level = class\n"
    )

    out = pytester.runpytest("-v", "--regsmart")

    assert any("diff_level" in x for x in out.errlines)


def test_report_header_shows_diff_level(selection_project):
    pytester, repo = selection_project
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")

    out = pytester.runpytest("--regsmart")

    assert any("Using --diff-level=function" in x for x in out.outlines)


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
    assert not any(
        "Time to run the regression test selection (s)" in x for x in out.outlines
    )


def test_no_diff_with_no_rank_plugin_does_nothing(selection_project):
    pytester, _repo = selection_project

    out = pytester.runpytest("-v", "--regsmart", "--no-rank")

    out.assert_outcomes(passed=4)
    assert any(
        "No diff detected and --no-rank enabled: pytest-regsmart is not doing anything."
        in x for x in out.outlines
    )


def test_conftest_untracked_runs_full_suite(selection_project):
    pytester, repo = selection_project
    (Path(repo.working_tree_dir) / "conftest.py").write_text(
        "# shared fixtures\n"
    )

    out = pytester.runpytest("-v", "--regsmart", "--no-rank")

    out.assert_outcomes(passed=4)
    assert _ran_files(out) == [
        "test_other.py",
        "test_service.py",
        "test_unrelated.py",
    ]
    assert any(
        "conftest.py changed: regression test selection was skipped." in x
        for x in out.outlines
    )
    assert not any(
        "Time to run the regression test selection (s)" in x for x in out.outlines
    )


def test_conftest_untracked_with_modified_file_runs_full_suite(selection_project):
    pytester, repo = selection_project
    _change(repo, "service.py", "def run():\n    return 42  # changed\n")
    (Path(repo.working_tree_dir) / "conftest.py").write_text(
        "# shared fixtures\n"
    )

    out = pytester.runpytest(
        "-v", "--regsmart", "--diff-level=function", "--no-rank"
    )

    out.assert_outcomes(passed=4)
    assert len(_ran_files(out)) == 3
    assert any(
        "conftest.py changed: regression test selection was skipped." in x
        for x in out.outlines
    )
    assert not any(
        "Time to run the regression test selection (s)" in x for x in out.outlines
    )


def test_conftest_only_warning_mentions_full_suite(selection_project):
    pytester, repo = selection_project
    (Path(repo.working_tree_dir) / "conftest.py").write_text(
        "# shared fixtures\n"
    )

    out = pytester.runpytest("-v", "--regsmart")

    out.assert_outcomes(passed=4)
    assert any(
        "The full suite will run." in x for x in out.outlines
    )


def test_no_merge_base_runs_full_suite_with_warning(selection_project):
    pytester, repo = selection_project
    repo.git.checkout("--orphan", "orphan-branch")
    repo.git.rm("-r", "--cached", ".")
    for f in ".gitignore", "pytest.ini", "service.py", "test_service.py", "test_other.py", "test_unrelated.py":
        repo.index.add([f])
    repo.index.commit("orphan baseline")

    # orphan branch shares no history with the base -> no merge base -> full suite
    out = pytester.runpytest("-v", "--regsmart", "--no-rank")

    out.assert_outcomes(passed=4)
    assert any(
        "No shared history" in x for x in out.outlines
    )


def test_detached_head_without_base_raises_clean_usage_error(selection_project):
    pytester, repo = selection_project
    repo.git.branch("-m", "dev")
    repo.git.checkout("--detach")

    # detached HEAD with no main/master, no origin/HEAD -> clean UsageError, no crash
    out = pytester.runpytest("--regsmart")

    assert any("Unable to determine the base branch" in x for x in out.errlines)
    assert not any("::" in x and "PASSED" in x for x in out.outlines)
