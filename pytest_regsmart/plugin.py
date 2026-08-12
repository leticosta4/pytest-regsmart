from __future__ import annotations

import argparse
import time

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
    DEFAULT_HIST_LEN,
    DEFAULT_RANK_LEVEL,
    DEFAULT_REPLAY,
    DEFAULT_SEED,
    DEFAULT_WEIGHT,
)
from .help_strings import (
    HIST_LEN_HELP,
    RANK_LEVEL_HELP,
    NO_RANK_HELP,
    PLUGIN_HELP,
    REPLAY_HELP,
    SEED_HELP,
    WEIGHT_HELP,
)
from .monitor import Monitor
from .ranking import rank_args, ranker
from .selection import git_manager, selector


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("regsmart", "pytest-regsmart")
    group._addoption(
        "--regsmart", #was the old --rank flag that activated the pytest-ranking default
        action="store_true",
        help=PLUGIN_HELP)

    #new flag here

    group._addoption(
        "--no-rank",
        action="store_true",
        default=False,
        help=NO_RANK_HELP,
        dest="no_rank") #maybe unecessary

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

    parser.addini("no_rank", NO_RANK_HELP, default=False)
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

        self.branch = ""  # will be set after selection
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

        if self.replay_file and self.weights == [0, 0]:
            raise argparse.ArgumentTypeError( #or usage error
                "--rank-replay cannot be used together with random order."
            )
        
        selection_start_time = time.time()
        selection = selector.run_rts()
        self.branch = selection.branch
        self.log["Time to run the regression test selection (s)"] = time.time() - selection_start_time

        if selection.affected_tests:
            selected_nodes = set(selection.affected_tests)
            items[:] = [item for item in items if item.nodeid.split("::")[0] in selected_nodes]  #filters only per file now, probably gotaa setup a flag

        if not selection.has_diff:
            self.warnings.append(
                "No diff detected: regression test selection was skipped."
            )
            if self.no_rank:
                self.warnings.append(
                    "No diff detected and --no-rank enabled: pytest-regsmart is not doing anything."
                )


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
        start_time = time.time()
        extractor.compute_test_features(
            self.config, self.monitor.test_reports, self.hist_len,
        )
        self.log["Time to collect test features (s)"] = (
            time.time() - start_time
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

    runner = PluginRunner(config)
    config.pluginmanager.register(runner)
