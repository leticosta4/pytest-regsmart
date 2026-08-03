from __future__ import annotations

from dataclasses import dataclass
from git import Repo


@dataclass
class DiffResult:
    modified_files: list[str] #staged+unstaged
    untracked_files: list[str] #completamente novo - talvez colocar uma flag futura para comparar tentar buscar só testes do unstages+untracked
    #depois ainda quero pegar a diff mais granular, talvez por linha ou conteudo de forma semantica?? n sei


def resolve_repo(repo_path: str = ".") -> Repo:
    return Repo(repo_path)


def get_git_diff(repo_path: str = ".") -> DiffResult:
    repo = resolve_repo(repo_path=repo_path)
    default_branch = "main"  #talvez eu deixe isso manualmente configuravel via flag depois

    merge_base_commit = repo.merge_base(default_branch, repo.head.commit)[0]  # https://git-scm.com/docs/git-merge-base#_description
    working_dir_diff = repo.git.diff(merge_base_commit, name_only=True).splitlines()
    untracked_diff = repo.untracked_files

    return DiffResult(
        modified_files=working_dir_diff,
        untracked_files=untracked_diff
    )
