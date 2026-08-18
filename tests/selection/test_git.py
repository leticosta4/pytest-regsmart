from __future__ import annotations

import os
from pathlib import Path

import pytest
from git import Repo
from git.exc import InvalidGitRepositoryError

from src.pytest_regsmart.selection.git_manager import (
    get_changed_line_ranges,
    get_default_repo_branch,
    get_git_diff,
    parse_diff_output,
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


def _diff(*lines: str) -> str:
    return "\n".join(lines)


@pytest.mark.parametrize(
    ("raw_diff", "expected"),
    [
        (
            _diff("--- a/a.py", "+++ b/a.py", "@@ -9,9 +9,9 @@", "-old", "+new"),
            {"a.py": [(9, 17)]},
        ),
        (
            _diff(
                "+++ b/a.py",
                "@@ -9,9 +9,9 @@",
                "-old",
                "+new",
                "@@ -20,2 +21,2 @@",
                "-x",
                "+y",
            ),
            {"a.py": [(9, 17), (21, 22)]},
        ),
        (
            _diff(
                "+++ b/a.py",
                "@@ -9,9 +9,9 @@",
                "-old",
                "+new",
                "+++ b/b.py",
                "@@ -1,26 +1,26 @@",
                "-a",
                "+b",
            ),
            {"a.py": [(9, 17)], "b.py": [(1, 26)]},
        ),
        (
            _diff("+++ b/novo.py", "@@ -0,0 +1,26 @@", "+def a():", "+    pass"),
            {"novo.py": [(1, 26)]},
        ),
        (
            _diff("+++ b/a.py", "@@ -10,3 +9,0 @@", "- a", "- b", "- c"),
            {"a.py": [(9, 9)]},
        ),
        (
            _diff(
                "+++ b/a.py",
                "@@ -1,3 +1,3 @@",
                "-a",
                "+b",
                "+++ /dev/null",
                "@@ -1,30 +0,0 @@",
                "- gone",
            ),
            {"a.py": [(1, 3)]},
        ),
        (_diff("+++ b/a.py", "@@ -18 +18 @@", "-x", "+y"), {"a.py": [(18, 18)]}),
        (
            _diff(
                "--- a/x.py",
                "+++ b/x.py",
                "@@ -1,3 +1,4 @@",
                " def a():",
                "-    return 1",
                "+    return 2",
                "+++     comentario estranho",
                "+    mais codigo",
                "@@ -20,2 +21,2 @@",
                "-def b():",
                "+def b():",
            ),
            {"x.py": [(1, 4), (21, 22)]},
        ),
    ],
    ids=[
        "single hunk edit",
        "multiple hunks same file",
        "multiple files",
        "new file addition",
        "pure deletion anchors on new_start",
        "deleted file ignored and does not contaminate",
        "hunk without count",
        "added line starting with '++ ' does not corrupt",
    ],
)
def test_parse_diff_output(raw_diff, expected):
    assert parse_diff_output(raw_diff) == expected


@pytest.mark.parametrize(
    ("original", "edited", "expected"),
    [
        ("a\nb\nc\n", "a\nB\nc\n", {"file.py": [(2, 2)]}),
        ("a\nb\nc\n", "a\nb\nX\nY\nc\n", {"file.py": [(3, 4)]}),
        ("a\nb\nc\n", "a\nc\n", {"file.py": [(1, 1)]}),
    ],
    ids=[
        "single line edit",
        "insert two lines",
        "delete one line anchors on new_start",
    ],
)
def test_get_changed_line_ranges_edits(git_repo, commit_file, original, edited, expected):
    commit_file("file.py", original)
    git_repo.git.branch("-m", "main")
    (Path(git_repo.working_tree_dir) / "file.py").write_text(edited)

    assert get_changed_line_ranges(str(git_repo.working_tree_dir)) == expected


def test_get_changed_line_ranges_committed_on_feature_branch(git_repo, commit_file):
    commit_file("file.py", "a\nb\nc\n")
    git_repo.git.branch("-m", "main")
    git_repo.git.checkout("-b", "feature")
    filepath = Path(git_repo.working_tree_dir) / "file.py"
    filepath.write_text("a\nB\nc\n")
    git_repo.index.add("file.py")
    git_repo.index.commit("edit line 2")

    assert get_changed_line_ranges(str(git_repo.working_tree_dir)) == {"file.py": [(2, 2)]}


def test_get_changed_line_ranges_deleted_file_absent(git_repo, commit_file):
    commit_file("file.py", "a\nb\nc\n")
    git_repo.git.branch("-m", "main")
    os.remove(Path(git_repo.working_tree_dir) / "file.py")

    assert get_changed_line_ranges(str(git_repo.working_tree_dir)) == {}


def test_get_changed_line_ranges_no_commits(tmp_path):
    Repo.init(tmp_path)

    assert get_changed_line_ranges(str(tmp_path)) == {}


def test_get_git_diff_deleted_file(git_repo, commit_file):
    commit_file("file_a.py")
    commit_file("file_b.py")
    git_repo.git.branch("-m", "main")
    os.remove(Path(git_repo.working_tree_dir) / "file_a.py")

    result = get_git_diff(str(git_repo.working_tree_dir))

    assert result.deleted_files == ["file_a.py"]
    assert "file_a.py" in result.modified_files


def test_get_git_diff_no_deleted_files(git_repo, commit_file):
    commit_file("file_a.py")
    git_repo.git.branch("-m", "main")

    result = get_git_diff(str(git_repo.working_tree_dir))

    assert result.deleted_files == []
