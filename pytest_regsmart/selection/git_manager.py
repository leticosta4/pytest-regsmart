from __future__ import annotations

import os
import re
from dataclasses import dataclass

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

@dataclass
class DiffResult:
    modified_files: list[str] #staged+unstaged
    untracked_files: list[str] #brand new files - maybe add a future flag to look only at unstaged+untracked tests
    used_branch: str
    deleted_files: list[str] | None = None


def resolve_repo(repo_path: str = ".") -> Repo:
    return Repo(repo_path)


def verify_git_repo(repo_path: str = ".") -> bool:
    try:
        resolve_repo(repo_path)
        return True
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False


def get_default_repo_branch(repo: Repo) -> str:
    try: #for when the repo has a remote (origin/HEAD)
        symbolic_ref = repo.git.symbolic_ref('refs/remotes/origin/HEAD')
        return symbolic_ref.split('/')[-1] #the last part of the ref is the branch name
    except GitCommandError:
        pass

    
    branch_names = [branch.name for branch in repo.branches] #fall back to main/master if not found
    for candidate in ("main", "master"):
        if candidate in branch_names:
            return candidate

    try:
        return repo.active_branch.name
    except TypeError:  # detached head
        raise ValueError(
            "Unable to determine the default branch." #no origin/HEAD, no main/master, no active branch
        ) from None


def _is_deleted(repo: Repo, merge_base_hash: str, path: str) -> bool:
    """True se o arquivo foi apagado do disco, mas ainda existe no commit-base."""
    if os.path.exists(os.path.join(repo.working_tree_dir, path)):
        return False
    try:
        repo.git.show(f"{merge_base_hash}:{path}")
        return True
    except GitCommandError:
        return False


def get_git_diff(repo_path: str = ".") -> DiffResult:
    repo = resolve_repo(repo_path=repo_path)

    if not repo.head.is_valid(): #repo has no commits yet (just git init); only check the untracked diff
        return DiffResult(
            modified_files=[],
            untracked_files=repo.untracked_files,
            used_branch=""
        )

    default_branch = get_default_repo_branch(repo) #maybe make this configurable via a flag later

    merge_base_commit = repo.merge_base(default_branch, repo.head.commit)[0]  # https://git-scm.com/docs/git-merge-base#_description
    working_dir_diff = repo.git.diff(merge_base_commit, name_only=True).splitlines()
    deleted_files = [path for path in working_dir_diff if _is_deleted(repo, merge_base_commit.hexsha, path)]
    untracked_diff = repo.untracked_files

    return DiffResult(
        modified_files=working_dir_diff,
        untracked_files=untracked_diff,
        deleted_files=deleted_files,
        used_branch=default_branch
    )


def parse_diff_output(raw_diff: str) -> dict[str, list[tuple[int, int]]]:
    """Parses `git diff -U0` and returns the changed line ranges for each file from the entire repo"""
    changed_line_ranges: dict[str, list[tuple[int, int]]] = {}
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

        hunk_match = HUNK_HEADER.match(line)
        if not hunk_match:
            continue

        # filters the hunk header: @@ -1,10 +1,12 @@ to get the start and end lines
        new_start_line = int(hunk_match.group(1))
        new_count = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1  # it's 1 if the hunk is a single line change (e.g., +1)
        new_end_line = new_start_line if new_count == 0 else new_start_line + new_count - 1  # has the same value as start_line if the change is just deletion

        # get the changed line ranges for the current modified file
        changed_line_ranges.setdefault(current_file, []).append((new_start_line, new_end_line))

    return changed_line_ranges


def get_changed_line_ranges(repo_path: str = ".") -> dict[str, list[tuple[int, int]]]:
    repo = resolve_repo(repo_path=repo_path)
    if not repo.head.is_valid():
        return {}
    
    default_branch = get_default_repo_branch(repo)
    merge_base_commit = repo.merge_base(default_branch, repo.head.commit)[0]
    raw_diff = repo.git.diff(merge_base_commit, unified=0)

    return parse_diff_output(raw_diff)
