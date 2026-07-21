from __future__ import annotations

from tests.fake_test_data import (
    test_a_method,
    test_b_class,
    test_c_put,
    test_class_one,
    test_method_one,
    test_put_one,
)


def test_logging(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one
    )

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=2, failed=1)
    log_text = (
        "Using --rank-weight",
        "Using --rank-level",
        "Using --rank-hist-len",
        "Using --rank-seed",
        "Time to reorder tests (s)",
        "Time to collect test features (s)",
    )

    header = "= pytest-regsmart summary info ="
    assert len([x for x in out.outlines if header in x]) == 0
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 0

    args = ["-v", "--rank"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=2, failed=1)
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 6


def test_invalid_weight(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one
    )
    args = ["-v", "--rank", "--rank-weight=1-3-2"]
    out = mytester.runpytest(*args)
    error_msg = "Cannot parse input for `--rank-weight`."
    assert any(error_msg in x for x in out.errlines)

    args = ["-v", "--rank", "--rank-weight=1-3-x"]
    out = mytester.runpytest(*args)
    error_msg = "Cannot parse input for `--rank-weight`."
    assert any(error_msg in x for x in out.errlines)


def test_random_order(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one,
        test_class_one=test_class_one,
    )

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)
    log_text = (
        "Using --rank-weight",
        "Using --rank-level",
        "Using --rank-hist-len",
        "Using --rank-seed",
        "Time to reorder tests (s)",
        "Time to collect test features (s)",
    )
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 0

    args = ["-v", "--rank"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 6

    args = ["-v", "--rank", "--rank-weight=0-0"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)
    log_text = (
        "Using --rank-seed=",
    )
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 1
    test_lines_default1 = [x for x in out.outlines if "::" in x]

    args = ["-v", "--rank", "--rank-weight=0.0-0.0", "--rank-seed=8"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)
    log_text = (
        "Using --rank-seed=8",
    )
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 1
    test_lines_1 = [x for x in out.outlines if "::" in x]

    args = ["-v", "--rank", "--rank-weight=0-0", "--rank-seed=16"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)
    log_text = (
        "Using --rank-seed=16",
    )
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 1
    test_lines_2 = [x for x in out.outlines if "::" in x]

    assert test_lines_default1 != test_lines_1 != test_lines_2


def test_xdist(mytester):
    mytester.makepyfile(
        test_put_one=test_put_one,
    )

    args = ["-v", "--rank", "-n", "auto", "--rank-weight=0-0"]
    out = mytester.runpytest(*args)
    assert len([x for x in out.outlines if x.startswith("ERROR")]) == 0


def test_invalid_level(mytester):
    mytester.makepyfile(
        test_a_method=test_a_method,
        test_b_class=test_b_class,
        test_c_put=test_c_put,
    )

    args = ["-v", "--rank", "--rank-level=class"]
    out = mytester.runpytest(*args)
    error_msg = "Invalid input for `--rank-level`."
    assert any(error_msg in x for x in out.errlines)
