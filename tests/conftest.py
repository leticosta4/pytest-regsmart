from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def mytester(pytester):
    pytester.makefile(
        ".ini",
        pytest="""
            [pytest]
            console_output_style = classic
            """,
    )
    yield pytester
