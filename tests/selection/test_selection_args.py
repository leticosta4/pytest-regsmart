import argparse

import pytest

from src.pytest_regsmart.const import DIFF_LEVEL
from src.pytest_regsmart.selection.selection_args import (
    level_type,
    parse_diff_level,
)


class _FakeConfig:
    def __init__(self, option: DIFF_LEVEL, ini: str = ""):
        self._option = option
        self._ini = ini

    def getoption(self, _name: str) -> DIFF_LEVEL:
        return self._option

    def getini(self, _name: str) -> str:
        return self._ini


def test_level_type_accepts_valid_levels():
    assert level_type("file") is DIFF_LEVEL.FILE
    assert level_type("function") is DIFF_LEVEL.FUNCTION


def test_level_type_rejects_invalid_level():
    with pytest.raises(argparse.ArgumentTypeError, match="--diff-level"):
        level_type("line")


def test_parse_diff_level_cli_value_wins_over_ini():
    config = _FakeConfig(option=DIFF_LEVEL.FILE, ini="function")

    assert parse_diff_level(config) is DIFF_LEVEL.FILE


def test_parse_diff_level_ini_used_when_cli_has_default():
    config = _FakeConfig(option=DIFF_LEVEL.FUNCTION, ini="file")

    assert parse_diff_level(config) is DIFF_LEVEL.FILE


def test_parse_diff_level_default_when_ini_unset():
    config = _FakeConfig(option=DIFF_LEVEL.FUNCTION, ini="")

    assert parse_diff_level(config) is DIFF_LEVEL.FUNCTION


def test_parse_diff_level_invalid_ini_value_raises_usage_error():
    config = _FakeConfig(option=DIFF_LEVEL.FUNCTION, ini="class")

    with pytest.raises(pytest.UsageError, match="diff_level"):
        parse_diff_level(config)
