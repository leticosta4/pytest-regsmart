from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo
from git.exc import InvalidGitRepositoryError, GitCommandError

from pytest_regsmart.selector import get_git_diff, DiffResult


def _init_repo(path: Path) -> Repo:
    repo = Repo.init(path)
    writer = repo.config_writer()
    writer.set_value("user", "name", "Test")
    writer.set_value("user", "email", "test@test.com")
    writer.release()
    return repo


def _commit_file(repo: Repo, filename: str, content: str = "") -> Path:
    filepath = Path(repo.working_tree_dir) / filename
    filepath.write_text(content)
    repo.index.add(filename)
    repo.index.commit(f"Add {filename}")
    return filepath


def test_commits_ahead_of_main(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_file(repo, "file_a.py")
    repo.git.branch("-m", "main")
    repo.git.checkout("-b", "feature")
    _commit_file(repo, "file_b.py")

    result = get_git_diff(str(tmp_path))

    assert "file_b.py" in result.modified_files
    assert "file_a.py" not in result.modified_files


def test_with_unstaged_changes(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_file(repo, "file_a.py", "original")
    repo.git.branch("-m", "main")
    filepath = Path(repo.working_tree_dir) / "file_a.py"
    filepath.write_text("modified")

    result = get_git_diff(str(tmp_path))

    assert "file_a.py" in result.modified_files


def test_with_untracked_files(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_file(repo, "file_a.py")
    repo.git.branch("-m", "main")
    untracked = Path(repo.working_tree_dir) / "new_file.py"
    untracked.write_text("new")

    result = get_git_diff(str(tmp_path))

    assert "new_file.py" in result.untracked_files
    assert "file_a.py" not in result.modified_files


def test_combined(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_file(repo, "file_a.py", "original")
    repo.git.branch("-m", "main")
    repo.git.checkout("-b", "feature")
    _commit_file(repo, "file_b.py")
    (Path(repo.working_tree_dir) / "file_a.py").write_text("unstaged")
    (Path(repo.working_tree_dir) / "new_file.py").write_text("untracked")

    result = get_git_diff(str(tmp_path))

    assert "file_b.py" in result.modified_files
    assert "file_a.py" in result.modified_files
    assert "new_file.py" in result.untracked_files


def test_no_changes(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_file(repo, "file_a.py")
    repo.git.branch("-m", "main")

    result = get_git_diff(str(tmp_path))

    assert result.modified_files == []
    assert result.untracked_files == []


def test_not_a_repo(tmp_path):
    with pytest.raises(InvalidGitRepositoryError):
        get_git_diff(str(tmp_path))


def test_no_main_branch(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_file(repo, "file_a.py")
    repo.git.branch("-m", "develop")

    with pytest.raises(GitCommandError):
        get_git_diff(str(tmp_path))
