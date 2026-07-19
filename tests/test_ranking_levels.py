from __future__ import annotations

import textwrap

from tests.fake_test_data import (
    test_a_method,
    test_a_method_two,
    test_b_class,
    test_c_put,
    test_c_put_ordered,
)


def test_put_level_ranking(mytester):
    mytester.makepyfile(
        test_a_method=test_a_method,
        test_b_class=test_b_class,
        test_c_put=test_c_put,
    )

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=13, failed=2)

    args = ["-v", "--rank", "--rank-level=put"]
    out = mytester.runpytest(*args)

    out.assert_outcomes(passed=13, failed=2)
    out.stdout.fnmatch_lines(
        [
            "test_c_put.py::test_a_put_unordered[0.1] PASSED",
            "test_c_put.py::test_b_put_ordered[0.15] PASSED",
            "test_c_put.py::test_a_put_unordered[0.2] PASSED",
            "test_c_put.py::test_b_put_ordered[0.25] PASSED",
            "test_c_put.py::test_a_put_unordered[0.3] PASSED",
            "test_c_put.py::test_b_put_ordered[0.35] PASSED",
            "test_c_put.py::test_a_put_unordered[0.4] PASSED",
            "test_c_put.py::test_b_put_ordered[0.45] PASSED",
            "test_a_method.py::test_b_fast_fail FAILED",
            "test_c_put.py::test_b_put_ordered[0.55] PASSED",
            "test_b_class.py::TestClassA::test_a_fast PASSED",
            "test_a_method.py::test_c_medium PASSED",
            "test_b_class.py::TestClassA::test_c_medium PASSED",
            "test_a_method.py::test_a_slow PASSED",
            "test_b_class.py::TestClassA::test_b_slow_fail FAILED"
        ],
        consecutive=True
    )


def test_function_level_ranking(mytester):
    mytester.makepyfile(
        test_a_method=test_a_method,
        test_b_class=test_b_class,
        test_c_put=test_c_put_ordered,
    )

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=9, failed=2)

    args = ["-v", "--rank", "--rank-level=function"]
    out = mytester.runpytest(*args)

    out.assert_outcomes(passed=9, failed=2)
    out.stdout.fnmatch_lines(
        [
            "test_c_put.py::test_b_put_ordered[0.45] PASSED",
            "test_c_put.py::test_b_put_ordered[0.25] PASSED",
            "test_c_put.py::test_b_put_ordered[0.55] PASSED",
            "test_c_put.py::test_b_put_ordered[0.35] PASSED",
            "test_c_put.py::test_b_put_ordered[0.15] PASSED",
            "test_a_method.py::test_b_fast_fail FAILED",
            "test_b_class.py::TestClassA::test_a_fast PASSED",
            "test_a_method.py::test_c_medium PASSED",
            "test_b_class.py::TestClassA::test_c_medium PASSED",
            "test_a_method.py::test_a_slow PASSED",
            "test_b_class.py::TestClassA::test_b_slow_fail FAILED",
        ],
        consecutive=True
    )


def test_module_level_ranking(mytester):
    mytester.makepyfile(
        test_a_method=test_a_method,
        test_b_class=test_b_class,
        test_c_put=test_c_put_ordered,
    )

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=9, failed=2)

    args = ["-v", "--rank", "--rank-level=module"]
    out = mytester.runpytest(*args)

    out.assert_outcomes(passed=9, failed=2)
    out.stdout.fnmatch_lines(
        [
            "test_c_put.py::test_b_put_ordered[0.45] PASSED",
            "test_c_put.py::test_b_put_ordered[0.25] PASSED",
            "test_c_put.py::test_b_put_ordered[0.55] PASSED",
            "test_c_put.py::test_b_put_ordered[0.35] PASSED",
            "test_c_put.py::test_b_put_ordered[0.15] PASSED",
            "test_a_method.py::test_a_slow PASSED",
            "test_a_method.py::test_b_fast_fail FAILED",
            "test_a_method.py::test_c_medium PASSED",
            "test_b_class.py::TestClassA::test_a_fast PASSED",
            "test_b_class.py::TestClassA::test_b_slow_fail FAILED",
            "test_b_class.py::TestClassA::test_c_medium PASSED",
        ],
        consecutive=True
    )


def test_dir_level_ranking(mytester):
    a = mytester.mkdir("a")
    a.joinpath("test_a_method.py").write_text(
        textwrap.dedent(test_a_method))
    a.joinpath("test_b_class.py").write_text(
        textwrap.dedent(test_b_class))
    b = mytester.mkdir("b")
    b.joinpath("test_c_put.py").write_text(
        textwrap.dedent(test_c_put_ordered))

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=9, failed=2)

    args = ["-v", "--rank", "--rank-level=dir"]
    out = mytester.runpytest(*args)

    out.assert_outcomes(passed=9, failed=2)
    out.stdout.fnmatch_lines(
        [
            "b/test_c_put.py::test_b_put_ordered[0.45] PASSED",
            "b/test_c_put.py::test_b_put_ordered[0.25] PASSED",
            "b/test_c_put.py::test_b_put_ordered[0.55] PASSED",
            "b/test_c_put.py::test_b_put_ordered[0.35] PASSED",
            "b/test_c_put.py::test_b_put_ordered[0.15] PASSED",
            "a/test_a_method.py::test_a_slow PASSED",
            "a/test_a_method.py::test_b_fast_fail FAILED",
            "a/test_a_method.py::test_c_medium PASSED",
            "a/test_b_class.py::TestClassA::test_a_fast PASSED",
            "a/test_b_class.py::TestClassA::test_b_slow_fail FAILED",
            "a/test_b_class.py::TestClassA::test_c_medium PASSED",
        ],
        consecutive=True
    )


def test_function_level_ranking_with_duplicate_methods(mytester):
    mytester.makepyfile(
        test_a_method=test_a_method,
        test_a_method_two=test_a_method_two,
        test_b_class=test_b_class,
        test_c_put=test_c_put_ordered,
    )

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=11, failed=3)

    args = ["-v", "--rank", "--rank-level=function"]
    out = mytester.runpytest(*args)

    out.assert_outcomes(passed=11, failed=3)
    out.stdout.fnmatch_lines(
        [
            "test_a_method_two.py::test_b_fast_fail FAILED",
            "test_a_method_two.py::test_c_medium PASSED",
            "test_a_method_two.py::test_a_slow PASSED",
            "test_c_put.py::test_b_put_ordered[0.45] PASSED",
            "test_c_put.py::test_b_put_ordered[0.25] PASSED",
            "test_c_put.py::test_b_put_ordered[0.55] PASSED",
            "test_c_put.py::test_b_put_ordered[0.35] PASSED",
            "test_c_put.py::test_b_put_ordered[0.15] PASSED",
            "test_a_method.py::test_b_fast_fail FAILED",
            "test_b_class.py::TestClassA::test_a_fast PASSED",
            "test_a_method.py::test_c_medium PASSED",
            "test_b_class.py::TestClassA::test_c_medium PASSED",
            "test_a_method.py::test_a_slow PASSED",
            "test_b_class.py::TestClassA::test_b_slow_fail FAILED",
        ],
        consecutive=True
    )
