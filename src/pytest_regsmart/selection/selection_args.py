import argparse

from ..const import DEFAULT_DIFF_LEVEL, DIFF_LEVEL

def level_type(string: str) -> str:
    "Check level format."
    if string == DEFAULT_DIFF_LEVEL:
        return string
    try:
        valid_levels = [i.value for i in DIFF_LEVEL]
        assert string in valid_levels
        return string
    except AssertionError:
        raise argparse.ArgumentTypeError(
            "Invalid input for `--diff-level`."
            + " Please run `pytest --help` for instruction."
        ) from None


def parse_diff_level(config) -> str:
    """Get selected level for git diff, non-default CLI overrides ini file input."""  #i need to decide if it's gonna be settable via ini/config file
    level = config.getoption("--diff-level")
    if level == DEFAULT_DIFF_LEVEL:
        ini_val = config.getini("diff_level")
        level = ini_val if ini_val else level
    return level
