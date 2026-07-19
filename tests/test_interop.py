from __future__ import annotations

from tests.fake_test_data import test_a_method, test_dependency, test_order


def test_order_dependency_marker(mytester):
    mytester.makepyfile(
        test_a_method=test_a_method,
        test_order=test_order,
        test_dependency=test_dependency,
    )

    args = ["-v"]
    out = mytester.runpytest(*args)
    out.assert_outcomes(passed=8, failed=1, xfailed=1)

    args = ["-v", "--rank"]
    out = mytester.runpytest(*args)

    out.assert_outcomes(passed=8, failed=1, xfailed=1)
    out.stdout.fnmatch_lines(
        [
            "test_dependency.py::test_a XFAIL (deliberate fail)",
            "test_dependency.py::test_b PASSED",
            "test_dependency.py::test_c PASSED",
            "test_dependency.py::test_d PASSED",
            "test_dependency.py::test_e PASSED",
            "test_order.py::test_foo PASSED",
            "test_order.py::test_bar PASSED",
            "test_a_method.py::test_b_fast_fail FAILED",
            "test_a_method.py::test_c_medium PASSED",
            "test_a_method.py::test_a_slow PASSED",
        ],
        consecutive=True
    )
