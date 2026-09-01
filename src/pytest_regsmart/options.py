from __future__ import annotations

import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
 
from .const import (
    DEFAULT_DIFF_LEVEL,
    DEFAULT_HIST_LEN,
    DEFAULT_RANK_LEVEL,
    DEFAULT_REPLAY,
    DEFAULT_SEED,
    DEFAULT_WEIGHT,
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
from .ranking import rank_args
from .selection import git_manager, selection_args


def add_options(parser: Parser) -> None:
    group = parser.getgroup("regsmart", "pytest-regsmart")
 
    group._addoption(
        "--regsmart",  # was the old --rank flag that activated the pytest-ranking default
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
 
 
def add_ini_options(parser: Parser) -> None:
    parser.addini("diff_level", DIFF_LEVEL_HELP, default=DEFAULT_DIFF_LEVEL.value)
    parser.addini("no_rank", NO_RANK_HELP, type="bool", default=False)
    parser.addini("rank_weight", WEIGHT_HELP, default=DEFAULT_WEIGHT)
    parser.addini("rank_replay", REPLAY_HELP, default=DEFAULT_REPLAY)
    parser.addini("rank_level", RANK_LEVEL_HELP, default=DEFAULT_RANK_LEVEL.value)
    parser.addini("rank_hist_len", HIST_LEN_HELP, default=DEFAULT_HIST_LEN)
    parser.addini("rank_seed", SEED_HELP, default=DEFAULT_SEED)


def validate_options(config: Config) -> None:
    """Valida combinações inválidas de flags antes de o plugin ser registrado."""
    if config.getoption("--regsmart") and config.getoption("--no-rank"):
        for arg in config.invocation_params.args:
            if arg.startswith("--rank-"):
                raise pytest.UsageError(
                    "--no-rank cannot be used together with other ranking flags. It excludes RTP."
                )
 
    if config.getoption("--regsmart") and not git_manager.verify_git_repo():
        raise pytest.UsageError("--regsmart requires a git repository.")
 
    if config.getoption("--rank-replay") and config.getoption("--rank-weight") == "0-0":
        raise pytest.UsageError(
            "--rank-replay cannot be used together with random order."
        )
