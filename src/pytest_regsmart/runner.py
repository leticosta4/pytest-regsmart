from __future__ import annotations
 
import pytest
from _pytest.config import Config
from _pytest.main import Session
from _pytest.nodes import Item
from _pytest.reports import TestReport
from _pytest.terminal import TerminalReporter
 
from . import reporter as reporter_mod
from .config import PluginConfig
from .monitor import Monitor
from .ranking import extractor, ranker
from .selection import selector
 
 
class PluginRunner:  #pytest hooks
    def __init__(self, config: Config, plugin_config: PluginConfig) -> None:
        self.config = config
        self.plugin_config = plugin_config
        self.log: dict = {}
        self.warnings: list[str] = []
        self.monitor = Monitor()

 
    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: list[Item]) -> None:
        if not self.config.getoption("--regsmart"):
            return
 
        plugin = self.plugin_config
        selection = selector.run_rts(level=plugin.diff_level, log_dict=self.log)
        plugin.branch = selection.branch

 
        self._collect_selection_warnings(selection, plugin.no_rank)
 
        if selection.affected_tests:
            selector.filter_pytest_items_for_rtp(items, set(selection.affected_tests), plugin.diff_level)
 
        if not plugin.no_rank:
            ranker.run_rtp(
                items, plugin.level, plugin.weights, plugin.replay_file, plugin.seed, self.log,
                lambda feature_name, items, reverse:
                    extractor.load_feature(self.config, feature_name, items, reverse),
            )


    def _collect_selection_warnings(self, selection, no_rank: bool) -> None:
        """warning messages according to RTS resullt"""
        if selection.no_merge_base:
            self.warnings.append(
                f"No shared history with base branch '{selection.branch}': regression test "
                "selection was skipped. The full suite will run. The value set for "
                "'--diff-level' was ignored."
            )

        elif not selection.has_diff:
            self.warnings.append(
                "No diff detected: regression test selection was skipped. The value set "
                "for '--diff-level' was ignored."
            )
            if no_rank:
                self.warnings.append(
                    "No diff detected and --no-rank enabled: pytest-regsmart is not doing anything."
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

 
    def pytest_runtest_logreport(self, report: TestReport) -> None:
        self.monitor.pytest_runtest_logreport(report)

 
    def pytest_report_header(self, config: Config) -> str | None:
        return reporter_mod.pytest_report_header(config)

 
    def pytest_sessionfinish(self, session: Session, exitstatus: int) -> None:
        extractor.compute_test_features(
            self.config, self.monitor.test_reports, self.plugin_config.hist_len, self.log,
        )


    def pytest_terminal_summary(
        self,
        terminalreporter: TerminalReporter,
        exitstatus: int,
        config: Config,
    ) -> None:
        if self.config.getoption("--regsmart"):
            reporter_mod.pytest_terminal_summary(
                terminalreporter, self.log, self.warnings, branch=self.plugin_config.branch,
            )
