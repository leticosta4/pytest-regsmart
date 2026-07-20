from __future__ import annotations

from _pytest.config import Config
from _pytest.terminal import TerminalReporter


def pytest_report_header(config: Config) -> str | None:
    """Report plugin configurations before test session starts."""
    if not config.getoption("--rank"):
        return None
    weight = config.getoption("--rank-weight")
    replay = config.getoption("--rank-replay")
    level = config.getoption("--rank-level")
    hist_len = config.getoption("--rank-hist-len")
    random_seed = config.getoption("--rank-seed")
    return "\n".join([
        f"Using --rank-weight={weight}",
        f"Using --rank-level={level}",
        f"Using --rank-hist-len={hist_len}",
        f"Using --rank-seed={random_seed}",
        f"Using --rank-replay={replay}",
    ])


def pytest_terminal_summary(
    terminalreporter: TerminalReporter,
    log_dict: dict,
) -> None:
    """Report plugin runtime when it is enabled."""
    tr = terminalreporter
    tr._tw.sep("=", "pytest-regsmart summary info")
    for k, v in log_dict.items():
        tr._tw.line(f"{k}: {v}")
