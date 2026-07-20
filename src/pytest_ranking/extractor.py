from __future__ import annotations

import os

from _pytest.config import Config
from _pytest.reports import TestReport

from .args import min_max_normalization
from .const import DATA_DIR


def load_feature(
    config: Config,
    feature_name: str,
    items: list,
    reverse: bool,
) -> list[float]:
    """Load and normalize test-wise feature data from cache."""
    key = os.path.join(DATA_DIR, feature_name)
    values = config.cache.get(key, {})
    values = [values.get(item.nodeid, 0) for item in items]
    values = min_max_normalization(values)
    if reverse:
        values = 1 - values
    return values.tolist()


def compute_test_features(
    config: Config,
    test_reports: list[TestReport],
    hist_len: int,
) -> None:
    """Persist last_durations and num_runs_since_fail to cache."""
    key = os.path.join(DATA_DIR, "last_durations")
    last_durations = config.cache.get(key, {})
    for report in test_reports:
        last_durations[report.nodeid] = round(report.duration, 3)
    config.cache.set(key, last_durations)

    key = os.path.join(DATA_DIR, "num_runs_since_fail")
    num_runs_since_fail = config.cache.get(key, {})
    for report in test_reports:
        if report.outcome == "failed":
            num_runs_since_fail[report.nodeid] = 0
        else:
            num_runs_since_fail[report.nodeid] = min(
                hist_len,
                num_runs_since_fail.get(report.nodeid, 0) + 1,
            )
    config.cache.set(key, num_runs_since_fail)
