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

from . import args
from . import extractor
from . import ranker
from . import reporter as reporter_mod
from .const import DEFAULT_HIST_LEN, DEFAULT_LEVEL, DEFAULT_REPLAY, DEFAULT_SEED, DEFAULT_WEIGHT
from .help_strings import (
    HIST_LEN_HELP, LEVEL_HELP, PLUGIN_HELP,
    REPLAY_HELP, SEED_HELP, WEIGHT_HELP,
)
from .monitor import Monitor


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("rank", "pytest-ranking")
    group._addoption(
        "--rank",
        action="store_true",
        help=PLUGIN_HELP)

    group._addoption(
        "--rank-level",
        action="store",
        type=args.level_type,
        default=DEFAULT_LEVEL,
        dest="rank_level",
        help=LEVEL_HELP)

    group._addoption(
        "--rank-weight",
        action="store",
        type=args.weight_type,
        default=DEFAULT_WEIGHT,
        dest="rank_weight",
        help=WEIGHT_HELP)

    group._addoption(
        "--rank-replay",
        action="store",
        type=args.replay_type,
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

    parser.addini("rank_weight", WEIGHT_HELP, default=DEFAULT_WEIGHT)
    parser.addini("rank_replay", REPLAY_HELP, default=DEFAULT_REPLAY)
    parser.addini("rank_level", LEVEL_HELP, default=DEFAULT_LEVEL)
    parser.addini("rank_hist_len", HIST_LEN_HELP, default=DEFAULT_HIST_LEN)
    parser.addini("rank_seed", SEED_HELP, default=DEFAULT_SEED)


class RTPRunner:
    """Plugin class."""
    def __init__(self, config: Config) -> None:
        self.config = config
        self.log = {}
        self.monitor = Monitor()

        self.weights = args.parse_rtp_weights(config)
        self.level = args.parse_rtp_level(config)
        self.replay_file = args.parse_replay(config)
        self.hist_len = args.parse_hist_len(config)
        self.seed = args.parse_seed(config)


    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: list[Item]) -> None:
        if not self.config.getoption("--rank"):
            return
        if self.replay_file and self.weights == [0, 0]:
            raise argparse.ArgumentTypeError(
                "--rank-replay cannot be used together with random order."
            )
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
        if self.config.getoption("--rank"):
            reporter_mod.pytest_terminal_summary(terminalreporter, self.log)


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    runner = RTPRunner(config)
    config.pluginmanager.register(runner)
