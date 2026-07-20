from __future__ import annotations

import argparse

import numpy as np

from .const import DEFAULT_HIST_LEN, DEFAULT_LEVEL, DEFAULT_REPLAY, DEFAULT_SEED, DEFAULT_WEIGHT, LEVEL


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
        )


def level_type(string: str) -> str:
    "Check level format."
    if string == DEFAULT_LEVEL:
        return string
    try:
        valid_levels = [i.value for i in LEVEL]
        assert string in valid_levels
        return string
    except AssertionError:
        raise argparse.ArgumentTypeError(
            "Invalid input for `--rank-level`."
            + " Please run `pytest --help` for instruction."
        )


def replay_type(string: str) -> str:
    "Check replay file format."
    if string == DEFAULT_REPLAY:
        return string
    try:
        with open(string) as f:
            _ = f.readlines()
        return string
    except Exception:
        raise argparse.ArgumentTypeError(
            "File provided to `--rank-replay` cannot be read."
            + " Please run `pytest --help` for instruction."
        )


def min_max_normalization(x: list[float]) -> np.ndarray:
    x = np.array(x)
    x_range = (np.max(x) - np.min(x))
    x = (x - np.min(x)) / x_range if x_range else np.zeros(len(x))
    return x


def parse_rtp_weights(config) -> list[float]:
    """Get weights, non-default CLI overrides ini file input."""
    weights = config.getoption("--rank-weight")
    if weights == DEFAULT_WEIGHT:
        ini_val = config.getini("rank_weight")
        weights = ini_val if ini_val else weights
    weights = weights.split("-")
    weights = [float(w) for w in weights]
    weight_sum = sum(weights)
    if weight_sum == 0:
        return [0, 0]
    return [w_i / weight_sum for w_i in weights]


def parse_rtp_level(config) -> str:
    """Get test group level, non-default CLI overrides ini file input."""
    level = config.getoption("--rank-level")
    if level == DEFAULT_LEVEL:
        ini_val = config.getini("rank_level")
        level = ini_val if ini_val else level
    return level


def parse_replay(config) -> str | None:
    """Get replay file, non-default CLI overrides ini file input."""
    replay_file = config.getoption("--rank-replay")
    if replay_file == DEFAULT_REPLAY:
        ini_val = config.getini("rank_replay")
        replay_file = ini_val if ini_val else replay_file
    return replay_file


def parse_hist_len(config) -> int:
    """Get history length, non-default CLI overrides ini file input."""
    hist_len = config.getoption("--rank-hist-len")
    if hist_len == DEFAULT_HIST_LEN:
        ini_val = config.getini("rank_hist_len")
        hist_len = ini_val if ini_val else hist_len
    return int(hist_len)


def parse_seed(config) -> int:
    """Get random seed, non-default CLI overrides ini file input."""
    rand_seed = config.getoption("--rank-seed")
    if rand_seed == DEFAULT_SEED:
        ini_val = config.getini("rank_seed")
        rand_seed = ini_val if ini_val else rand_seed
    return int(rand_seed)
