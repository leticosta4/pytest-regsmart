from __future__ import annotations

import collections
import os
import random
import time

import numpy as np

from .const import LEVEL


def get_test_group(nodeid: str, level: LEVEL) -> str:
    """Get test group at different granularity levels.

    Given: folder/testfile.py::TestClass::testmethod[param1]
        - function: folder/testfile.py::TestClass::testmethod
        - module: folder/testfile.py

    Otherwise, treat each PUT as a unique test group.
    """
    test_without_param = nodeid.split("[")[0]
    test_file_path = test_without_param.split("::")[0]
    if level == LEVEL.FUNCTION:
        return test_without_param
    elif level == LEVEL.MODULE:
        return test_file_path
    else:
        return nodeid


def get_ranking(scores: dict, level: LEVEL, init_order: dict) -> dict:
    """Aggregate scores per test group, sort, return {nodeid: rank}."""
    tests = []
    for nodeid, score in scores.items():
        group = get_test_group(nodeid, level)
        tests.append([nodeid, score, group])

    group_scores = collections.defaultdict(list)
    for _, score, group in tests:
        group_scores[group].append(score)
    agg_group_scores = {
        group: np.mean(score_list)
        for group, score_list in group_scores.items()
    }

    tests.sort(
        key=lambda x: (agg_group_scores[x[2]], init_order[x[0]]),
    )
    return {
        nodeid: rank
        for rank, (nodeid, _, _) in enumerate(tests)
    }


def run_rtp(
    items: list,
    level: LEVEL,
    weights: list[float],
    replay_file: str | None,
    seed: int,
    log_dict: dict,
    load_feature_fn,
) -> None:
    """Orquestra o ranqueamento: replay, random, ou híbrido."""
    init_order = {item.nodeid: i for i, item in enumerate(items)}
    start_time = time.time()

    scores: dict = {}
    if replay_file and os.path.exists(replay_file):
        with open(replay_file) as f:
            test_list = [x.strip() for x in f.readlines()]
            scores = {x: i for i, x in enumerate(test_list)}
    elif weights == [0, 0]:
        items.sort(key=lambda item: item.nodeid)
        random.seed(seed)
        scores = {item.nodeid: random.random() for item in items}
    else:
        w_time, w_fail = weights
        h_time = load_feature_fn("last_durations", items, True)
        h_fail = load_feature_fn("num_runs_since_fail", items, True)

        scores = {
            item.nodeid: -(
                h_time[i] * w_time + h_fail[i] * w_fail
            )
            for i, item in enumerate(items)
        }

    rank = get_ranking(scores, level, init_order)

    od_items = [
        item for item in items
        if item.get_closest_marker("order")
        or item.get_closest_marker("dependency")
    ]
    nod_items = [
        item for item in items
        if item not in od_items
    ]
    nod_items.sort(
        key=lambda item: (
            rank.get(item.nodeid, 0), init_order[item.nodeid]
        )
    )
    items[:] = od_items + nod_items

    log_dict["Time to reorder tests (s)"] = time.time() - start_time
