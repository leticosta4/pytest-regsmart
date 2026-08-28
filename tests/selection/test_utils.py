from __future__ import annotations

import os

from src.pytest_regsmart.utils import _is_conftest


def test_is_conftest_root_level():
    assert _is_conftest("conftest.py") is True


def test_is_conftest_in_subdirectory():
    assert _is_conftest("tests/conftest.py") is True
    assert _is_conftest(os.path.join("tests", "conftest.py")) is True
    assert _is_conftest("tests/sub/conftest.py") is True


def test_is_conftest_rejects_other_files():
    assert _is_conftest("service.py") is False
    assert _is_conftest("test_conftest.py") is False
    assert _is_conftest("conftest.py.bak") is False
    assert _is_conftest("CONFTEST.py") is False