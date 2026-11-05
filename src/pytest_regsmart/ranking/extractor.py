from __future__ import annotations

import os
import time

from _pytest.config import Config
from _pytest.reports import TestReport

from ..const import DATA_DIR
from .rank_args import min_max_normalization


def load_feature(
    config: Config,
    feature_name: str,
    items: list,
    reverse: bool,
) -> list[float]:
    """Load and normalize test-wise feature data from cache."""
    cache = getattr(config, "cache", None)
    if cache is None:  # cacheprovider disabled: no history to rank by
        return [0.0] * len(items)
    key = os.path.join(DATA_DIR, feature_name)
    values = cache.get(key, {})
    values = [values.get(item.nodeid, 0) for item in items]
    values = min_max_normalization(values)
    if reverse:
        values = 1 - values
    return values.tolist()


def compute_test_features(
    config: Config,
    test_reports: list[TestReport],
    hist_len: int,
    log_dict: dict | None = None,
) -> None:
    """Persist last_durations and num_runs_since_fail to cache."""
    cache = getattr(config, "cache", None)
    if cache is None:  # cacheprovider disabled (-p no:cacheprovider): nothing to persist
        return
    start_time = time.time()
    key = os.path.join(DATA_DIR, "last_durations")
    last_durations = cache.get(key, {})
    for report in test_reports:
        last_durations[report.nodeid] = round(report.duration, 3)
    cache.set(key, last_durations)

    key = os.path.join(DATA_DIR, "num_runs_since_fail")
    num_runs_since_fail = cache.get(key, {})
    for report in test_reports:
        if report.outcome == "failed":
            num_runs_since_fail[report.nodeid] = 0
        else:
            num_runs_since_fail[report.nodeid] = min(
                hist_len,
                num_runs_since_fail.get(report.nodeid, 0) + 1,
            )
    cache.set(key, num_runs_since_fail)

    if log_dict is not None:
        log_dict["Time to collect test features (s)"] = time.time() - start_time
