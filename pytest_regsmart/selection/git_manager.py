from __future__ import annotations

from dataclasses import dataclass

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError


@dataclass
class DiffResult:
    modified_files: list[str] #staged+unstaged
    untracked_files: list[str] #completamente novo - talvez colocar uma flag futura para comparar tentar buscar só testes do unstages+untracked
    #depois ainda quero pegar a diff mais granular, talvez por linha ou conteudo de forma semantica?? n sei


def resolve_repo(repo_path: str = ".") -> Repo:
    return Repo(repo_path)


def verify_git_repo(repo_path: str = ".") -> bool:
    try:
        resolve_repo(repo_path)
        return True
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False


def get_default_repo_branch(repo: Repo) -> str:
    try: #pra quando o repo tem remote (origin/HEAD)
        symbolic_ref = repo.git.symbolic_ref('refs/remotes/origin/HEAD')
        return symbolic_ref.split('/')[-1] #a ultima parte da ref é o nome da branch
    except GitCommandError:
        pass

    
    branch_names = [branch.name for branch in repo.branches] #se nao tiver vai tentar buscar main/master
    for candidate in ("main", "master"):
        if candidate in branch_names:
            return candidate

    try:
        return repo.active_branch.name
    except TypeError:  # detached head
        raise ValueError(
            "Unable to determine the default branch." #sem origin/HEAD, sem main/master e sem branch ativa
        ) from None


def get_git_diff(repo_path: str = ".") -> DiffResult:
    repo = resolve_repo(repo_path=repo_path)

    if not repo.head.is_valid(): #se o repo nao tem commits (mas tem git init), vou só checar o diff untracked
        return DiffResult(
            modified_files=[],
            untracked_files=repo.untracked_files
        )

    default_branch = get_default_repo_branch(repo) #talvez eu deixe isso manualmente configuravel via flag depois

    merge_base_commit = repo.merge_base(default_branch, repo.head.commit)[0]  # https://git-scm.com/docs/git-merge-base#_description
    working_dir_diff = repo.git.diff(merge_base_commit, name_only=True).splitlines()
    untracked_diff = repo.untracked_files

    return DiffResult(
        modified_files=working_dir_diff,
        untracked_files=untracked_diff
    )
