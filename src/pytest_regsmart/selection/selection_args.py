import argparse

from ..const import DEFAULT_DIFF_LEVEL, DIFF_LEVEL


def level_type(string: str) -> DIFF_LEVEL:
    "Check level format."
    try:
        return DIFF_LEVEL(string)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Invalid input for `--diff-level`."
            + " Please run `pytest --help` for instruction."
        ) from None


def parse_diff_level(config) -> DIFF_LEVEL:
    """Get selected level for git diff, non-default CLI overrides ini file input."""  #i need to decide if it's gonna be settable via ini/config file
    level = config.getoption("--diff-level")
    if level == DEFAULT_DIFF_LEVEL:
        ini_val = config.getini("diff_level")
        level = ini_val if ini_val else level
    return DIFF_LEVEL(level)
