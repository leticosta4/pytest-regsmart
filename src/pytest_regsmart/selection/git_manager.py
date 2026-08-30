from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TypeAlias

import pytest
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from pytest_regsmart.const import DEFAULT_DIFF_LEVEL, DIFF_HUNK_HEADER, DIFF_LEVEL

LineRange: TypeAlias = tuple[int, int]
ChangedLineRanges: TypeAlias = dict[str, list[LineRange]]


@dataclass
class DiffResult:
    used_branch: str
    modified_files: list[str] = field(default_factory=list) #staged+unstaged
    untracked_files: list[str] = field(default_factory=list) #brand new files - maybe add a future flag to look only at unstaged+untracked tests
    deleted_files: list[str] = field(default_factory=list)
    changed_line_ranges: ChangedLineRanges = field(default_factory=dict)  #only for DIFF_LEVEL.FUNCTION
    no_merge_base: bool = False  #base resolved, but no shared history with HEAD


def resolve_repo(repo_path: str = ".") -> Repo:
    return Repo(repo_path)


def verify_git_repo(repo_path: str = ".") -> bool:
    try:
        resolve_repo(repo_path)
        return True
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False


def get_default_repo_branch(repo: Repo) -> str | None:
    """Resolve the base branch to compare against the *destination* a commit
    is headed to (never the current branch). Returns None when it cannot be determined,
    which happens on shallow clones in CI where the destination branch isn't fetched."""
    # 1. GitHub Actions PR: explicit destination via env var
    if base_ref := os.environ.get("GITHUB_BASE_REF"):
        return base_ref

    # 2. Remote default (origin/HEAD)
    try: #for when the repo has a remote (origin/HEAD)
        symbolic_ref = repo.git.symbolic_ref('refs/remotes/origin/HEAD')
        return symbolic_ref.split('/')[-1] #the last part of the ref is the branch name
    except GitCommandError:
        pass

    # 3. Local main/master
    branch_names = [branch.name for branch in repo.branches]
    for candidate in ("main", "master"):
        if candidate in branch_names:
            return candidate

    # 4. Upstream tracking of the current branch (if it targets a different branch)
    try:
        active = repo.active_branch
    except TypeError:  # detached HEAD
        active = None
    if active is not None:
        try:
            upstream = active.tracking_branch()
            if upstream is not None:
                upstream_name = upstream.name.lstrip("./")
                if upstream_name.split('/')[-1] != active.name:
                    return upstream_name
        except (AttributeError, GitCommandError):
            pass

    return None


def _is_deleted(repo: Repo, merge_base_hash: str, path: str) -> bool:
    """True se o arquivo foi apagado do disco, mas ainda existe no commit-base."""
    if os.path.exists(os.path.join(repo.working_tree_dir, path)):
        return False
    try:
        repo.git.show(f"{merge_base_hash}:{path}")
        return True
    except GitCommandError:
        return False


def parse_diff_output(raw_diff: str) -> ChangedLineRanges:
    """Parses `git diff -U0` and returns the changed line ranges for each file from the entire repo"""
    changed_line_ranges: ChangedLineRanges = {}
    current_file: str | None = None

    for line in raw_diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.removeprefix("+++ b/")
            continue
        if line == "+++ /dev/null":
            current_file = None
            continue
        if current_file is None:
            continue

        hunk_match = DIFF_HUNK_HEADER.match(line)
        if not hunk_match:
            continue

        # filters the hunk header: @@ -1,10 +1,12 @@ to get the start and end lines
        new_start_line = int(hunk_match.group(1))
        new_count = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1  # it's 1 if the hunk is a single line change (e.g., +1)
        new_end_line = new_start_line if new_count == 0 else new_start_line + new_count - 1  # has the same value as start_line if the change is just deletion

        # get the changed line ranges for the current modified file
        changed_line_ranges.setdefault(current_file, []).append((new_start_line, new_end_line))

    return changed_line_ranges


def get_git_diff(repo_path: str = ".", diff_level: DIFF_LEVEL = DEFAULT_DIFF_LEVEL) -> DiffResult:
    repo = resolve_repo(repo_path=repo_path)
    untracked_diff = repo.untracked_files

    if not repo.head.is_valid(): #repo has no commits yet (just git init); only check the untracked diff
        return DiffResult(
            modified_files=[],
            untracked_files=untracked_diff,
            used_branch=""
        )

    default_branch = get_default_repo_branch(repo) #maybe make this configurable via a flag later
    if default_branch is None:
        raise pytest.UsageError(
            "Unable to determine the base branch to compare against. "
            "This usually happens on a shallow clone (CI often uses fetch-depth: 1), "
            "where the destination branch (e.g. `main`) is not available locally. "
            "Fix by using `fetch-depth: 0` in your checkout step (e.g. actions/checkout), "
            "by fetching the base branch, or by setting the GITHUB_BASE_REF environment variable."
        )

    try:
        merge_base_commit = repo.merge_base(default_branch, repo.head.commit)[0]  # https://git-scm.com/docs/git-merge-base#_description
    except (IndexError, GitCommandError):
        # Base resolved but shares no history with HEAD (e.g. unrelated first commit).
        return DiffResult(
            modified_files=[],
            untracked_files=untracked_diff,
            used_branch=default_branch,
            no_merge_base=True,
        )

    working_dir_diff = repo.git.diff(merge_base_commit, name_only=True).splitlines()
    deleted_files = [path for path in working_dir_diff if _is_deleted(repo, merge_base_commit.hexsha, path)]

    if diff_level == DIFF_LEVEL.FUNCTION:
        raw_diff = repo.git.diff(merge_base_commit, unified=0)
            
        return DiffResult(
                    modified_files=working_dir_diff,
                    untracked_files=untracked_diff,
                    deleted_files=deleted_files,
                    used_branch=default_branch,
                    changed_line_ranges=parse_diff_output(raw_diff)
            )
    
    return DiffResult(
        modified_files=working_dir_diff,
        untracked_files=untracked_diff,
        deleted_files=deleted_files,
        used_branch=default_branch
    )
