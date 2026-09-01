import argparse
import os

import pytest


def _find_py_files(working_dir: str) -> list[str]: 
    excludes = [".venv", ".git", "__pycache__", "dist", "build", "venv", "site-packages"]

    py_files = []
    for dirpath, dirnames, filenames in os.walk(working_dir):
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.endswith(".egg-info")]  # keep only core directories to check
        for filename in filenames:
            if filename.endswith(".py"):
                py_files.append(os.path.join(dirpath, filename)) #build the full path
    return py_files


def _is_test_file(filepath: str) -> bool:
    filename = os.path.basename(filepath)
    return filename.startswith("test_") or filename.endswith("_test.py")


def _is_conftest(filepath: str) -> bool:
    return os.path.basename(filepath) == "conftest.py"


def _resolve_ini_value(config, cli_opt, default, ini_key, type_fn):
    value = config.getoption(cli_opt)
    if value == default:
        ini_val = config.getini(ini_key)
        value = ini_val if ini_val else value
    try:
        return type_fn(value)
    except argparse.ArgumentTypeError as e:
        raise pytest.UsageError(f"Invalid value for '{ini_key}' in pytest.ini: {e}") from None
