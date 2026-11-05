from __future__ import annotations

from types import SimpleNamespace

import pytest

from pytest_regsmart.ranking.ranker import RANKING_TIME_KEY
from pytest_regsmart.runner import PluginRunner
from pytest_regsmart.selection.selector import SELECTION_TIME_KEY
from tests.fake_test_data import test_method_one


def _runner_with_worker_info(worker_info: list[dict]) -> PluginRunner:
    runner = PluginRunner.__new__(PluginRunner)
    runner._xdist_worker_info = worker_info
    runner.log = {}
    runner.warnings = []
    runner.plugin_config = SimpleNamespace(branch=None)
    return runner


def test_merge_xdist_worker_info_uses_maximum_durations():
    runner = _runner_with_worker_info(
        [
            {
                "log": {SELECTION_TIME_KEY: 0.2, RANKING_TIME_KEY: 0.4},
                "warnings": [],
                "branch": "main",
            },
            {
                "log": {SELECTION_TIME_KEY: 0.5, RANKING_TIME_KEY: 0.1},
                "warnings": [],
                "branch": "main",
            },
        ]
    )

    runner._merge_xdist_worker_info()

    assert runner.log[SELECTION_TIME_KEY] == 0.5
    assert runner.log[RANKING_TIME_KEY] == 0.4
    assert runner.plugin_config.branch == "main"


def test_merge_xdist_worker_info_warns_on_branch_conflict():
    runner = _runner_with_worker_info(
        [
            {"log": {}, "warnings": ["worker warning"], "branch": "main"},
            {"log": {}, "warnings": ["worker warning"], "branch": "master"},
        ]
    )

    runner._merge_xdist_worker_info()

    assert runner.plugin_config.branch is None
    assert any("different comparison branches: main, master" in w for w in runner.warnings)
    assert runner.warnings.count("worker warning") == 1


def test_selection_error_runs_full_suite_with_warning(mytester, monkeypatch):
    def boom(**kwargs):
        raise KeyError("top")

    monkeypatch.setattr("pytest_regsmart.selection.selector.run_rts_with_fallback", boom)
    mytester.makepyfile(test_method_one=test_method_one)

    out = mytester.runpytest("-v", "--regsmart", "--no-rank")

    out.assert_outcomes(passed=2, failed=1)
    assert out.ret != pytest.ExitCode.INTERNAL_ERROR
    out.stdout.fnmatch_lines(["*Regression test selection failed (KeyError: 'top')*full suite will run*"])


def test_ranking_error_keeps_collection_order_with_warning(mytester, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("bad history")

    monkeypatch.setattr("pytest_regsmart.ranking.ranker.run_rtp", boom)
    mytester.makepyfile(test_method_one=test_method_one)

    out = mytester.runpytest("-v", "--regsmart")

    out.assert_outcomes(passed=2, failed=1)
    out.stdout.fnmatch_lines([
        "test_method_one.py::test_slow PASSED",
        "test_method_one.py::test_fast_fail FAILED",
        "test_method_one.py::test_medium PASSED",
    ], consecutive=True)
    out.stdout.fnmatch_lines(["*Test prioritization failed (ValueError: bad history)*"])


@pytest.mark.parametrize("args", [
    (),
    ("--regsmart",),
    ("--regsmart", "--no-rank"),
])
def test_disabled_cacheprovider_does_not_crash(mytester, args):
    mytester.makepyfile(test_method_one=test_method_one)

    out = mytester.runpytest("-v", "-p", "no:cacheprovider", *args)

    out.assert_outcomes(passed=2, failed=1)
    assert "AttributeError" not in str(out.outlines + out.errlines)


def test_selection_usage_error_is_not_swallowed(mytester, monkeypatch):
    def usage_error(**kwargs):
        raise pytest.UsageError("main/master was not found")

    monkeypatch.setattr(
        "pytest_regsmart.selection.selector.run_rts_with_fallback", usage_error
    )
    mytester.makepyfile(test_method_one=test_method_one)

    out = mytester.runpytest("--regsmart", "--no-rank")

    assert out.ret == pytest.ExitCode.USAGE_ERROR
    assert any("main/master was not found" in x for x in out.errlines)
