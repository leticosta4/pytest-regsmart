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
        "Using --ranking-weight",
        "Using --ranking-level",
        "Using --ranking-hist-len",
        "Using --ranking-seed",
        "Time to run the regression test prioritization (s)",
        "Time to collect test features (s)",
    )

    header = "= pytest-regsmart summary info ="
    assert len([x for x in out.outlines if header in x]) == 0
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 0

    args = ["-v", "--regsmart"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=2, failed=1)
    assert len([x for x in out.outlines if x.startswith(log_text)]) == 6


def test_invalid_weight(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one
    )
    args = ["-v", "--regsmart", "--ranking-weight=1-3-2"]
    out = mytester.runpytest(*args)
    error_msg = "Cannot parse input for `--ranking-weight`."
    assert any(error_msg in x for x in out.errlines)

    args = ["-v", "--regsmart", "--ranking-weight=1-3-x"]
    out = mytester.runpytest(*args)
    error_msg = "Cannot parse input for `--ranking-weight`."
    assert any(error_msg in x for x in out.errlines)


def test_random_order(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one,
        test_class_one=test_class_one,
    )

    args = ["-v", "--regsmart", "--ranking-weight=0-0"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)
    assert len([x for x in out.outlines if x.startswith("Using --ranking-seed=")]) == 1
    test_lines_default1 = [x for x in out.outlines if "::" in x]

    args = ["-v", "--regsmart", "--ranking-weight=0.0-0.0", "--ranking-seed=8"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)
    assert len([x for x in out.outlines if x.startswith("Using --ranking-seed=8")]) == 1
    test_lines_1 = [x for x in out.outlines if "::" in x]

    args = ["-v", "--regsmart", "--ranking-weight=0-0", "--ranking-seed=16"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=4, failed=2)
    assert len([x for x in out.outlines if x.startswith("Using --ranking-seed=16")]) == 1
    test_lines_2 = [x for x in out.outlines if "::" in x]

    assert test_lines_default1 != test_lines_1 != test_lines_2


def test_xdist(mytester):
    mytester.makepyfile(
        test_put_one=test_put_one,
    )

    args = ["-v", "--regsmart", "-n", "auto", "--ranking-weight=0-0"]
    out = mytester.runpytest(*args)
    assert len([x for x in out.outlines if x.startswith("ERROR")]) == 0


def test_invalid_level(mytester):
    mytester.makepyfile(
        test_a_method=test_a_method,
        test_b_class=test_b_class,
        test_c_put=test_c_put,
    )

    args = ["-v", "--regsmart", "--ranking-level=class"]
    out = mytester.runpytest(*args)
    error_msg = "Invalid input for `--ranking-level`:"
    assert any(error_msg in x for x in out.errlines)


def test_summary_reports_used_branch(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one,
    )

    args = ["-v", "--regsmart"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=2, failed=1)
    assert any(
        x.startswith("Default branch used for comparison:")
        for x in out.outlines
    )
