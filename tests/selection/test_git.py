from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo
from git.exc import InvalidGitRepositoryError

from src.pytest_regsmart.selection.git_manager import (
    get_default_repo_branch,
    get_git_diff,
    verify_git_repo,
)


def test_verify_git_repo_true(git_repo, commit_file):
    commit_file("file_a.py")

    assert verify_git_repo(str(git_repo.working_tree_dir)) is True


def test_verify_git_repo_false(tmp_path):
    assert verify_git_repo(str(tmp_path)) is False


def test_verify_git_repo_nonexistent_path(tmp_path):
    assert verify_git_repo(str(tmp_path / "does-not-exist")) is False


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


def test_default_branch_is_main(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "main")

    assert get_default_repo_branch(git_repo) == "main"


def test_default_branch_is_master(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "master")

    assert get_default_repo_branch(git_repo) == "master"


def test_default_branch_feature_prefers_local_main(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "main")
    git_repo.git.checkout("-b", "feature")

    assert get_default_repo_branch(git_repo) == "main"


def test_default_branch_detached_with_local_main(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "main")
    git_repo.git.checkout("--detach")

    assert get_default_repo_branch(git_repo) == "main"


def test_get_git_diff_custom_default_branch(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "develop")

    result = get_git_diff(str(git_repo.working_tree_dir))

    assert result.modified_files == []
    assert result.untracked_files == []
    assert result.used_branch == "develop"


def test_get_git_diff_no_commits(tmp_path):
    Repo.init(tmp_path)
    (tmp_path / "new_file.py").write_text("new")

    result = get_git_diff(str(tmp_path))

    assert result.modified_files == []
    assert "new_file.py" in result.untracked_files
    assert result.used_branch == ""
