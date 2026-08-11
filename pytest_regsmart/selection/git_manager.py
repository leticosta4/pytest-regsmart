from __future__ import annotations

from dataclasses import dataclass

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError


@dataclass
class DiffResult:
    modified_files: list[str] #staged+unstaged
    untracked_files: list[str] #brand new files - maybe add a future flag to look only at unstaged+untracked tests
    #later I also want a more granular diff, maybe per line or by semantic content?? idk


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


def get_git_diff(repo_path: str = ".") -> DiffResult:
    repo = resolve_repo(repo_path=repo_path)

    if not repo.head.is_valid(): #repo has no commits yet (just git init); only check the untracked diff
        return DiffResult(
            modified_files=[],
            untracked_files=repo.untracked_files
        )

    default_branch = get_default_repo_branch(repo) #maybe make this configurable via a flag later

    merge_base_commit = repo.merge_base(default_branch, repo.head.commit)[0]  # https://git-scm.com/docs/git-merge-base#_description
    working_dir_diff = repo.git.diff(merge_base_commit, name_only=True).splitlines()
    untracked_diff = repo.untracked_files

    return DiffResult(
        modified_files=working_dir_diff,
        untracked_files=untracked_diff
    )
