from __future__ import annotations

from tests.fake_test_data import test_method_one


def test_regsmart_requires_git_repo(pytester):
    pytester.makepyfile(test_method_one=test_method_one)

    out = pytester.runpytest("--regsmart")

    assert any("--regsmart requires a git repository." in x for x in out.errlines)
    assert not any("::" in x and "PASSED" in x for x in out.outlines)
