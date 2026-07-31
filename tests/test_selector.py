from __future__ import annotations

from pathlib import Path

import pytest
from git.exc import GitCommandError, InvalidGitRepositoryError

from pytest_regsmart.selector import DiffResult, get_git_diff


def test_commits_ahead_of_main(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "main")
    git_repo.git.checkout("-b", "feature")
    commit_file("file_b.py")

    result = get_git_diff(str(git_repo.working_tree_dir))

    assert "file_b.py" in result.modified_files
    assert "file_a.py" not in result.modified_files


def test_with_unstaged_changes(git_repo, commit_file):
    commit_file("file_a.py", "original")
    git_repo.git.branch("-m", "main")
    filepath = Path(git_repo.working_tree_dir) / "file_a.py"
    filepath.write_text("modified")

    result = get_git_diff(str(git_repo.working_tree_dir))

    assert "file_a.py" in result.modified_files


def test_with_untracked_files(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "main")
    untracked = Path(git_repo.working_tree_dir) / "new_file.py"
    untracked.write_text("new")

    result = get_git_diff(str(git_repo.working_tree_dir))

    assert "new_file.py" in result.untracked_files
    assert "file_a.py" not in result.modified_files


def test_combined(git_repo, commit_file):
    commit_file("file_a.py", "original")
    git_repo.git.branch("-m", "main")
    git_repo.git.checkout("-b", "feature")
    commit_file("file_b.py")
    (Path(git_repo.working_tree_dir) / "file_a.py").write_text("unstaged")
    (Path(git_repo.working_tree_dir) / "new_file.py").write_text("untracked")

    result = get_git_diff(str(git_repo.working_tree_dir))

    assert "file_b.py" in result.modified_files
    assert "file_a.py" in result.modified_files
    assert "new_file.py" in result.untracked_files


def test_no_changes(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "main")

    result = get_git_diff(str(git_repo.working_tree_dir))

    assert result.modified_files == []
    assert result.untracked_files == []


def test_not_a_repo(tmp_path):
    with pytest.raises(InvalidGitRepositoryError):
        get_git_diff(str(tmp_path))


def test_no_main_branch(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "develop")

    with pytest.raises(GitCommandError):
        get_git_diff(str(git_repo.working_tree_dir))
