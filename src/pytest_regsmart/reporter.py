from __future__ import annotations

from _pytest.config import Config
from _pytest.terminal import TerminalReporter

from .ranking.ranking_args import parse_no_rank


def pytest_report_header(config: Config) -> str | None:
    """Report plugin configurations before test session starts."""

    if not config.getoption("--regsmart"):
        return None

    if parse_no_rank(config):
        return [
            "\nStarting RTS (Regression Test Selection)",
            "Using --no-rank (RTP disabled).",
        ]

    diff_level = config.getoption("--diff-level")
    weight = config.getoption("--ranking-weight")
    replay = config.getoption("--ranking-replay")
    ranking_level = config.getoption("--ranking-level")
    hist_len = config.getoption("--ranking-hist-len")
    random_seed = config.getoption("--ranking-seed")
    return [
        "\nStarting Smart Regression Test Management (RTS + RTP)",
    ] + [
        f"Using --diff-level={diff_level}",
        f"Using --ranking-weight={weight}",
        f"Using --ranking-level={ranking_level}",
        f"Using --ranking-hist-len={hist_len}",
        f"Using --ranking-seed={random_seed}",
        f"Using --ranking-replay={replay}",
    ]


def pytest_terminal_summary(
    terminalreporter: TerminalReporter,
    log_dict: dict,
    warnings: tuple[str, ...] = (),
    branch: str = "",
) -> None:
    """Report plugin runtime when it is enabled."""
    tr = terminalreporter
    tr._tw.sep("=", "pytest-regsmart summary info")
    if branch:
        tr._tw.line(f"Default branch used for comparison: {branch}")
    for w in warnings:
        tr._tw.line(f"WARNING: {w}")
    for k, v in log_dict.items():
        tr._tw.line(f"{k}: {v*1000:.2f} ms ({v} s)")
