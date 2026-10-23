from __future__ import annotations

from types import SimpleNamespace

from pytest_regsmart.ranking.ranker import RANKING_TIME_KEY
from pytest_regsmart.runner import PluginRunner
from pytest_regsmart.selection.selector import SELECTION_TIME_KEY


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
