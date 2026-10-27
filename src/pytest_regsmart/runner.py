from __future__ import annotations

import pytest
from _pytest.config import Config
from _pytest.main import Session
from _pytest.nodes import Item
from _pytest.reports import TestReport
from _pytest.terminal import TerminalReporter

from . import reporter as reporter_mod
from .config import PluginConfig
from .const import DIFF_SOURCE
from .monitor import Monitor
from .ranking import extractor, ranker
from .selection import selector

_XDIST_INFO_KEY = "pytest_regsmart"
_XDIST_LOG_KEYS = (
    selector.SELECTION_TIME_KEY,
    selector.SELECTION_TIME_KEY_FILE_LEVEL,
    ranker.RANKING_TIME_KEY,
)


class PluginRunner:  #pytest hooks
    def __init__(self, config: Config, plugin_config: PluginConfig) -> None:
        self.config = config
        self.plugin_config = plugin_config
        self.log: dict = {}
        self.warnings: list[str] = []
        self.monitor = Monitor()
        self._xdist_worker_info: list[dict] = []

 
    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: list[Item]) -> None:
        if not self.config.getoption("--regsmart"):
            return
 
        plugin = self.plugin_config

        if len(items) == 1:
            self.warnings.append(
                "RTS and RTP skipped: only 1 test was collected."
            )
            return

        selection = selector.run_rts_with_fallback(
            level=plugin.diff_level,
            log_dict=self.log,
            diff_source=plugin.diff_source,
        )
        plugin.branch = selection.branch
 
        self._collect_selection_warnings(selection, plugin.no_rank, plugin.diff_source)
 
        if selection.affected_tests:
            unfiltered = list(items)
            selector.filter_pytest_items_for_rtp(
                items, set(selection.affected_tests), selection.level
            )
            if not items:
                items[:] = unfiltered
                self.warnings.append(
                    "Selected tests matched no collected test (nodeid mismatch): "
                    "the full suite will run."
                )
 
        if not plugin.no_rank:
            if len(items) > 1:
                ranker.run_rtp(
                    items, plugin.level, plugin.weights, plugin.replay_file, plugin.seed, self.log,
                    lambda feature_name, items, reverse:
                        extractor.load_feature(self.config, feature_name, items, reverse),
                )
            elif len(items) == 1:
                self.warnings.append(
                    "RTP skipped: only 1 test was selected, nothing to reorder."
                )


    def _collect_selection_warnings(self, selection, no_rank: bool, diff_source) -> None:
        """warning messages according to RTS resullt"""
        if selection.no_merge_base:
            self.warnings.append(
                f"No shared history with base branch '{selection.branch}': regression test "
                "selection was skipped. The full suite will run. The value set for "
                "'--diff-level' was ignored."
            )

        elif not selection.has_diff:
            hint = (
                " Only committed changes are compared; commit your changes or pass "
                "--local-diff to select from the working tree."
                if diff_source == DIFF_SOURCE.COMMIT
                else ""
            )
            self.warnings.append(
                "No diff detected in Python files: regression test selection was skipped."
                f"{hint} The value set for '--diff-level' was ignored."
            )
            if no_rank:
                self.warnings.append(
                    "No diff detected in Python files and --no-rank enabled: pytest-regsmart is not doing anything."
                )

        elif selection.full_run:
            self.warnings.append(
                "conftest.py changed: regression test selection was skipped. The full suite "
                "will run. The value set for '--diff-level' was ignored."
            )
            if no_rank:
                self.warnings.append(
                    "conftest.py changed and --no-rank enabled: pytest-regsmart is not doing anything."
                )

        elif not selection.affected_tests:
            self.warnings.append(
                "Diff detected but no affected tests found at file level: "
                "running the full suite."
            )

        if selection.degraded_to_file:
            if selection.degraded_from_unresolved and selection.affected_tests:
                files = ", ".join(selection.unresolved_files)
                self.warnings.append(
                    "Function-level selection left "
                    f"{len(selection.unresolved_files)} file(s) unresolved "
                    f"({files}); falling back to file-level selection "
                    f"({len(selection.affected_tests)} test file(s))."
                )
            else:
                self.warnings.append(
                    "Function-level selection found no affected tests; falling back to "
                    f"file-level selection ({len(selection.affected_tests)} test file(s))."
                )

 
    def pytest_runtest_logreport(self, report: TestReport) -> None:
        self.monitor.pytest_runtest_logreport(report)

 
    def pytest_report_header(self, config: Config) -> str | None:
        return reporter_mod.pytest_report_header(config)

 
    def pytest_sessionfinish(self, session: Session, exitstatus: int) -> None:
        extractor.compute_test_features(
            self.config, self.monitor.test_reports, self.plugin_config.hist_len, self.log,
        )
        self.log["Tests executed"] = len(self.monitor.test_reports)

        workeroutput = getattr(self.config, "workeroutput", None)
        if workeroutput is not None and self.config.getoption("--regsmart"):
            workeroutput[_XDIST_INFO_KEY] = {
                "log": {key: self.log[key] for key in _XDIST_LOG_KEYS if key in self.log},
                "warnings": self.warnings,
                "branch": self.plugin_config.branch,
            }

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error) -> None:
        """Collect pytest-regsmart information returned by an xdist worker."""
        info = getattr(node, "workeroutput", {}).get(_XDIST_INFO_KEY)
        if info is not None:
            self._xdist_worker_info.append(info)

    def _merge_xdist_worker_info(self) -> None:
        if not self._xdist_worker_info:
            return

        # Workers perform collection, selection, and prioritization in parallel.
        # The maximum duration is the critical path before test execution starts.
        for key in _XDIST_LOG_KEYS:
            values = [
                info["log"][key]
                for info in self._xdist_worker_info
                if key in info["log"]
            ]
            if values:
                self.log[key] = max(values)

        branches = {info["branch"] for info in self._xdist_worker_info if info["branch"]}
        if len(branches) == 1:
            self.plugin_config.branch = branches.pop()
        elif len(branches) > 1:
            branches_string = ", ".join(sorted(branches))
            self.warnings.append(
                f"xdist workers used different comparison branches: {branches_string}"
            )

        for info in self._xdist_worker_info:
            for warning in info["warnings"]:
                if warning not in self.warnings:
                    self.warnings.append(warning)

    def pytest_terminal_summary(
        self,
        terminalreporter: TerminalReporter,
        exitstatus: int,
        config: Config,
    ) -> None:
        if self.config.getoption("--regsmart"):
            self._merge_xdist_worker_info()
            reporter_mod.pytest_terminal_summary(
                terminalreporter, self.log, self.warnings, branch=self.plugin_config.branch,
            )
