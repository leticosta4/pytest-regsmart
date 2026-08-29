from __future__ import annotations

import argparse

import numpy as np

from ..const import (
    DEFAULT_HIST_LEN,
    DEFAULT_RANK_LEVEL,
    DEFAULT_REPLAY,
    DEFAULT_SEED,
    DEFAULT_WEIGHT,
    RANK_LEVEL,
)
from ..utils import _resolve_ini_value


def weight_type(string: str) -> str:
    """Check weight format."""
    if string == DEFAULT_WEIGHT:
        return string
    try:
        weights = string.split("-")
        assert len(weights) == 2
        weights = [float(w) for w in weights]
        return string
    except (AssertionError, ValueError):
        raise argparse.ArgumentTypeError(
            "Cannot parse input for `--rank-weight`."
            + "Valid examples: 1-0, 0.4-0.2, and 2-7."
        ) from None


def level_type(string: str) -> str:
    "Check level format."
    if string == DEFAULT_RANK_LEVEL:
        return string
    try:
        valid_levels = [i.value for i in RANK_LEVEL]
        assert string in valid_levels
        return string
    except AssertionError:
        valid = ", ".join(item.value for item in RANK_LEVEL)
        raise argparse.ArgumentTypeError(
            f"Invalid input for `--rank-level`: '{string}'. Valid values: {valid}."
        ) from None


def replay_type(string: str) -> str:
    "Check replay file format."
    if string == DEFAULT_REPLAY:
        return string
    try:
        with open(string) as f:
            _ = f.readlines()
        return string
    except Exception:  # noqa: BLE001
        raise argparse.ArgumentTypeError(
            "File provided to `--rank-replay` cannot be read."
            + " Please run `pytest --help` for instruction."
        ) from None


def hist_len_type(string) -> int:
    "Check history length format."
    try:
        return int(string)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            f"Invalid input for `--rank-hist-len`: '{string}'. It must be an integer."
        ) from None


def seed_type(string) -> int:
    "Check seed format."
    try:
        return int(string)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            f"Invalid input for `--rank-seed`: '{string}'. It must be an integer."
        ) from None


def min_max_normalization(x: list[float]) -> np.ndarray:
    x = np.array(x)
    if x.size == 0:
        return x
    x_range = (np.max(x) - np.min(x))
    x = (x - np.min(x)) / x_range if x_range else np.zeros(len(x))
    return x


def parse_rtp_weights(config) -> list[float]:
    """Get weights, non-default CLI overrides ini file input."""
    weights = _resolve_ini_value(
        config,
        cli_opt="--rank-weight",
        default=DEFAULT_WEIGHT,
        ini_key="rank_weight",
        type_fn=weight_type,
    )

    weights = [float(w) for w in weights.split("-")]
    weight_sum = sum(weights)
    if weight_sum == 0:
        return [0, 0]
    return [w_i / weight_sum for w_i in weights]


def parse_rtp_level(config) -> str:
    """Get test group level, non-default CLI overrides ini file input."""
    return _resolve_ini_value(
        config,
        cli_opt="--rank-level",
        default=DEFAULT_RANK_LEVEL,
        ini_key="rank_level",
        type_fn=level_type,
    )


def parse_replay(config) -> str | None:
    """Get replay file, non-default CLI overrides ini file input."""
    return _resolve_ini_value(
        config,
        cli_opt="--rank-replay",
        default=DEFAULT_REPLAY,
        ini_key="rank_replay",
        type_fn=replay_type,
    )


def parse_hist_len(config) -> int:
    """Get history length, non-default CLI overrides ini file input."""
    return _resolve_ini_value(
        config,
        cli_opt="--rank-hist-len",
        default=DEFAULT_HIST_LEN,
        ini_key="rank_hist_len",
        type_fn=hist_len_type,
    )


def parse_seed(config) -> int:
    """Get random seed, non-default CLI overrides ini file input."""
    return _resolve_ini_value(
        config,
        cli_opt="--rank-seed",
        default=DEFAULT_SEED,
        ini_key="rank_seed",
        type_fn=seed_type,
    )


def parse_no_rank(config) -> bool:
    """Get no-rank option, non-default CLI overrides ini file input."""
    no_rtp = config.getoption("--no-rank")
    if not no_rtp:
        return config.getini("no_rank")
    return True
