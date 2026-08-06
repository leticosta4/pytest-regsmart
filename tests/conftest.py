from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

pytest_plugins = ["pytester"]


@pytest.fixture
def git_repo(tmp_path) -> Repo:
    repo = Repo.init(tmp_path)
    writer = repo.config_writer()
    writer.set_value("user", "name", "Test")
    writer.set_value("user", "email", "test@test.com")
    writer.release()
    return repo


@pytest.fixture
def commit_file(git_repo):
    def _commit_file(filename: str, content: str = "") -> Path:
        filepath = Path(git_repo.working_tree_dir) / filename
        filepath.write_text(content)
        git_repo.index.add(filename)
        git_repo.index.commit(f"Add {filename}")
        return filepath

    return _commit_file


@pytest.fixture
def mytester(pytester):
    pytester.makefile(
        ".ini",
        pytest="""
            [pytest]
            console_output_style = classic
            """,
    )
    repo = Repo.init(pytester.path)
    writer = repo.config_writer()
    writer.set_value("user", "name", "Test")
    writer.set_value("user", "email", "test@test.com")
    writer.release()
    if repo.active_branch.name != "main":
        repo.git.branch("-m", "main")
    (pytester.path / ".gitignore").write_text("__pycache__/\n")
    repo.index.add([".gitignore"])
    repo.index.commit("chore: baseline")
    yield pytester
