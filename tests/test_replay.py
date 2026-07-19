from __future__ import annotations

from tests.fake_test_data import (
    replay_order_one,
    test_a_method,
    test_class_one,
    test_method_one,
)


def test_replay(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one,
        test_class_one=test_class_one,
    )

    mytester.maketxtfile(
        replay_order=replay_order_one
    )

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)

    args = ["-v", "--rank", "--rank-replay=replay_order.txt"]
    out = mytester.runpytest(*args)

    out.assert_outcomes(passed=4, failed=2)
    out.stdout.fnmatch_lines(
        [
            "test_class_one.py::TestClassSample::test_fast PASSED",
            "test_class_one.py::TestClassSample::test_slow_fail FAILED",
            "test_method_one.py::test_medium PASSED",
            "test_method_one.py::test_fast_fail FAILED",
            "test_class_one.py::TestClassSample::test_medium PASSED",
            "test_method_one.py::test_slow PASSED",
        ],
        consecutive=True
    )


def test_replay_with_random(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one,
        test_class_one=test_class_one,
    )

    mytester.maketxtfile(
        replay_order=replay_order_one
    )

    args = [
        "-v",
        "--rank",
        "--rank-replay=replay_order.txt",
        "--rank-weight=0-0"
    ]
    out = mytester.runpytest(*args)
    error_msg = "--rank-replay cannot be used together with random order."
    assert len([x for x in out.outlines if error_msg in x]) == 1


def test_invalid_replay(mytester):
    mytester.makepyfile(
        test_a_method=test_a_method,
    )

    args = ["-v", "--rank", "--rank-replay=order.txt"]
    out = mytester.runpytest(*args)
    error_msg = "pytest: error: argument --rank-replay:" \
        + " File provided to `--rank-replay` cannot be read." \
        + " Please run `pytest --help` for instruction."
    assert len([x for x in out.errlines if x.startswith(error_msg)]) == 1
