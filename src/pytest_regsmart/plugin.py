from __future__ import annotations

import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.main import Session
from _pytest.nodes import Item
from _pytest.reports import TestReport
from _pytest.terminal import TerminalReporter

from . import extractor
from . import reporter as reporter_mod
from .const import (
    DEFAULT_DIFF_LEVEL,
    DEFAULT_HIST_LEN,
    DEFAULT_RANK_LEVEL,
    DEFAULT_REPLAY,
    DEFAULT_SEED,
    DEFAULT_WEIGHT,
    DIFF_LEVEL,
)
from .help_strings import (
    DIFF_LEVEL_HELP,
    HIST_LEN_HELP,
    NO_RANK_HELP,
    PLUGIN_HELP,
    RANK_LEVEL_HELP,
    REPLAY_HELP,
    SEED_HELP,
    WEIGHT_HELP,
)
from .monitor import Monitor
from .ranking import rank_args, ranker
from .selection import git_manager, selection_args, selector


def _validate_options(config: Config) -> None:
    if config.getoption("--regsmart") and config.getoption("--no-rank"):
        for arg in config.invocation_params.args:
            if arg.startswith("--rank-"):
                raise pytest.UsageError(
                    "--no-rank cannot be used together with other ranking flags. It excludes RTP."
                )

    if config.getoption("--regsmart") and not git_manager.verify_git_repo():
        raise pytest.UsageError(
            "--regsmart requires a git repository."
        )

    if config.getoption("--rank-replay") and config.getoption("--rank-weight") == "0-0":
        raise pytest.UsageError(
            "--rank-replay cannot be used together with random order."
        )


def _select_pytest_items_for_rtp(self, items, selected_nodes) -> None:
    items[:] = (
        [item for item in items if item.nodeid.split("::")[0] in selected_nodes] if self.diff_level == DIFF_LEVEL.FILE
        else [
            item
            for item in items
            if any(
                item.nodeid == selected_node
                or item.nodeid.startswith(f"{selected_node}[")
                for selected_node in selected_nodes
            )
        ]
    ) 


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("regsmart", "pytest-regsmart")
    group._addoption(
        "--regsmart", #was the old --rank flag that activated the pytest-ranking default
        action="store_true",
        help=PLUGIN_HELP)

    group.addoption(
        "--diff-level",
        action="store",
        type=selection_args.level_type,
        default=DEFAULT_DIFF_LEVEL,
        dest="diff_level",
        help=DIFF_LEVEL_HELP)

    group._addoption(
        "--no-rank",
        action="store_true",
        default=False,
        help=NO_RANK_HELP)

    group._addoption(
        "--rank-level",
        action="store",
        type=rank_args.level_type,
        default=DEFAULT_RANK_LEVEL,
        dest="rank_level",
        help=RANK_LEVEL_HELP)

    group._addoption(
        "--rank-weight",
        action="store",
        type=rank_args.weight_type,
        default=DEFAULT_WEIGHT,
        dest="rank_weight",
        help=WEIGHT_HELP)

    group._addoption(
        "--rank-replay",
        action="store",
        type=rank_args.replay_type,
        default=DEFAULT_REPLAY,
        dest="rank_replay",
        help=REPLAY_HELP)

    group._addoption(
        "--rank-hist-len",
        action="store",
        type=int,
        dest="rank_hist_len",
        default=DEFAULT_HIST_LEN,
        help=HIST_LEN_HELP)

    group._addoption(
        "--rank-seed",
        action="store",
        type=int,
        dest="rank_seed",
        default=DEFAULT_SEED,
        help=SEED_HELP)

    parser.addini("diff_level", DIFF_LEVEL_HELP, default=DEFAULT_DIFF_LEVEL)
    parser.addini("no_rank", NO_RANK_HELP, type="bool")
    parser.addini("rank_weight", WEIGHT_HELP, default=DEFAULT_WEIGHT)
    parser.addini("rank_replay", REPLAY_HELP, default=DEFAULT_REPLAY)
    parser.addini("rank_level", RANK_LEVEL_HELP, default=DEFAULT_RANK_LEVEL)
    parser.addini("rank_hist_len", HIST_LEN_HELP, default=DEFAULT_HIST_LEN)
    parser.addini("rank_seed", SEED_HELP, default=DEFAULT_SEED)


class PluginRunner:
    """Plugin class."""
    def __init__(self, config: Config) -> None:
        self.config = config
        self.log = {}
        self.warnings: list[str] = []
        self.monitor = Monitor()

        self.branch = str | None
        self.diff_level = selection_args.parse_diff_level(config)
        self.no_rank = rank_args.parse_no_rank(config)
        self.weights = rank_args.parse_rtp_weights(config)
        self.level = rank_args.parse_rtp_level(config)
        self.replay_file = rank_args.parse_replay(config)
        self.hist_len = rank_args.parse_hist_len(config)
        self.seed = rank_args.parse_seed(config)

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: list[Item]) -> None:
        if not self.config.getoption("--regsmart"):
            return
        
        selection = selector.run_rts(level=self.diff_level, log_dict=self.log)
        self.branch = selection.branch

        if not selection.has_diff:  #maybe i should separate return items though
            self.warnings.append(
                "No diff detected: regression test selection was skipped. The value set for '--diff-level' will be ignored."
            )
            if self.no_rank:
                self.warnings.append(
                    "No diff detected and --no-rank enabled: pytest-regsmart is not doing anything."
                )

        if selection.full_run:
            self.warnings.append(
                "conftest.py was modified: regression test selection was skipped. The value set for '--diff-level' will be ignored."
            )
            if self.no_rank:
                self.warnings.append(
                    "conftest diff and --no-rank enabled: pytest-regsmart is not doing anything."
                )

        if selection.affected_tests:
            selected_nodes = set(selection.affected_tests)

            _select_pytest_items_for_rtp(self, items, selected_nodes)

        if not self.no_rank:
            ranker.run_rtp(
                items, self.level, self.weights,
                self.replay_file, self.seed, self.log,
                lambda feature_name, items, reverse:
                    extractor.load_feature(self.config, feature_name, items, reverse),
            )


    def pytest_runtest_logreport(self, report: TestReport) -> None:
        self.monitor.pytest_runtest_logreport(report)


    def pytest_report_header(self, config: Config) -> str | None:
        return reporter_mod.pytest_report_header(config)

    def pytest_sessionfinish(self, session: Session, exitstatus: int) -> None:
        extractor.compute_test_features(
            self.config, self.monitor.test_reports, self.hist_len, self.log,
        )


    def pytest_terminal_summary(
            self,
            terminalreporter: TerminalReporter,
            exitstatus: int,
            config: Config) -> None:
        if self.config.getoption("--regsmart"):
            reporter_mod.pytest_terminal_summary(
                terminalreporter, self.log, self.warnings, branch=self.branch,
            )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    _validate_options(config)

    runner = PluginRunner(config)
    config.pluginmanager.register(runner)
