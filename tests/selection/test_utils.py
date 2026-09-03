from __future__ import annotations

import os

from src.pytest_regsmart.utils import _filter_python_files, _is_conftest


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


def test_filter_python_files_keeps_only_dot_py():
    files = ["service.py", "pyproject.toml", "tests/test_app.py", "README.md", ".gitignore"]
    assert _filter_python_files(files) == ["service.py", "tests/test_app.py"]


def test_filter_python_files_empty_list():
    assert _filter_python_files([]) == []


def test_filter_python_files_no_python():
    assert _filter_python_files(["pyproject.toml", "setup.cfg"]) == []