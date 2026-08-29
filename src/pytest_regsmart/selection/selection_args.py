import argparse

from ..const import DEFAULT_DIFF_LEVEL, DIFF_LEVEL
from ..utils import _resolve_ini_value


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
    """Get selected level for git diff, non-default CLI overrides ini file input."""
    return _resolve_ini_value(
        config,
        cli_opt="--diff-level",
        default=DEFAULT_DIFF_LEVEL,
        ini_key="diff_level",
        type_fn=level_type,
    )
