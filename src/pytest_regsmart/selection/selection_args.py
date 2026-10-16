import argparse

from ..const import DEFAULT_DIFF_LEVEL, DEFAULT_DIFF_SOURCE, DIFF_LEVEL, DIFF_SOURCE
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


def parse_diff_source(config) -> DIFF_SOURCE:
    """Get where the diff is read from, non-default CLI overrides ini file input.

    The plugin defaults to the committed diff; ``--local-diff`` (or the
    ``local_diff`` ini option) switches to the local, uncommitted changes.
    """
    if config.getoption("--local-diff") or config.getini("local_diff"):
        return DIFF_SOURCE.WORKTREE
    return DEFAULT_DIFF_SOURCE
