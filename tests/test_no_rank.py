from __future__ import annotations

import pytest

from tests.fake_test_data import test_method_one


def test_no_rank_without_regsmart(mytester):
    mytester.makepyfile(
        test_method_one=test_method_one,
    )
    args = ["-v", "--no-rank"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=2, failed=1)


def test_no_rank_disables_rtp(mytester):
    mytester.makepyfile(test_method_one=test_method_one)
    args = ["-v", "--regsmart", "--no-rank"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=2, failed=1)
    out.stdout.fnmatch_lines([
        "test_method_one.py::test_slow PASSED",
        "test_method_one.py::test_fast_fail FAILED",
        "test_method_one.py::test_medium PASSED",
    ], consecutive=True)


@pytest.mark.parametrize("ranking_flag", [
    "--rank-weight=0-1",
    "--rank-weight=1-0",
    "--rank-level=function",
    "--rank-hist-len=30",
    "--rank-seed=42",
])
def test_no_rank_with_ranking_flag_error(mytester, ranking_flag):
    mytester.makepyfile(test_method_one=test_method_one)
    args = ["-v", "--regsmart", "--no-rank", ranking_flag]
    out = mytester.runpytest(*args)
    assert "--no-rank cannot be used together" in str(out.errlines + out.outlines)


def test_no_rank_header_and_summary(mytester):
    mytester.makepyfile(test_method_one=test_method_one)
    args = ["-v", "--regsmart", "--no-rank"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=2, failed=1)

    assert any("Using --no-rank (RTP disabled)." in x for x in out.outlines)
    assert any("pytest-regsmart summary info" in x for x in out.outlines)
    assert any("Time to collect test features (s)" in x for x in out.outlines)

    log_lines = (
        "Using --rank-weight",
        "Using --rank-level",
        "Using --rank-hist-len",
        "Using --rank-seed",
    )
    assert len([x for x in out.outlines if x.startswith(log_lines)]) == 0
