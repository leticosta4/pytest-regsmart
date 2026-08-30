from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TypeAlias

import pytest
from git import Repo
from git.exc import BadName, GitCommandError, InvalidGitRepositoryError, NoSuchPathError

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


_DEFAULT_BRANCH_CANDIDATES = ("main", "master")


def resolve_base_ref(repo: Repo) -> str | None:
    """Ref que o git consegue resolver para a branch default (main/master):
    primeiro a branch local, depois a remote-tracking (origin/main) -- que e o
    que sobra depois do actions/checkout com fetch-depth: 0 em qualquer evento."""
    for branch in _DEFAULT_BRANCH_CANDIDATES:
        for ref in (branch, f"origin/{branch}"):
            try:
                repo.commit(ref)
            except (BadName, GitCommandError):
                continue
            return ref  # "main" local ou "origin/main"
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

    base_ref = resolve_base_ref(repo) #maybe make this configurable via a flag later
    if base_ref is None:
        raise pytest.UsageError(
            "main/master nao foi encontrada (nem local nem origin/main). "
            "Em CI raso (fetch-depth: 1) a base nao e buscada; use fetch-depth: 0 no "
            "actions/checkout, e garanta que a main tambem seja buscada "
            "(ex: `git fetch origin main:refs/remotes/origin/main`)."
        )

    try:
        merge_base_commit = repo.merge_base(base_ref, repo.head.commit)[0]  # https://git-scm.com/docs/git-merge-base#_description
    except (IndexError, GitCommandError):
        # Base resolved but shares no history with HEAD (e.g. unrelated first commit).
        return DiffResult(
            modified_files=[],
            untracked_files=untracked_diff,
            used_branch=base_ref,
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
                    used_branch=base_ref,
                    changed_line_ranges=parse_diff_output(raw_diff)
            )
    
    return DiffResult(
        modified_files=working_dir_diff,
        untracked_files=untracked_diff,
        deleted_files=deleted_files,
        used_branch=base_ref
    )
