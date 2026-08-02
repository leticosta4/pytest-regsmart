from __future__ import annotations

from dataclasses import dataclass

from ..const import resolve_repo
from .ast import get_dependency_graph


@dataclass
class DiffResult:
    modified_files: list[str] #staged+unstaged
    untracked_files: list[str] #completamente novo - talvez colocar uma flag futura para comparar tentar buscar só testes do unstages+untracked
    #depois ainda quero pegar a diff mais granular, talvez por linha ou conteudo de forma semantica?? n sei


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


def get_affected_tests(diff_result: DiffResult, short_graph) -> list[str]:
    pass


def run_rts():
    """[wip] Orquestra a seleção..."""

    diff_result = get_git_diff()  # noqa: F841
    imports_deps_graph = get_dependency_graph()  # noqa: F841  #talvez vou paralelizar isso com o git diff mais pra frente


#rodar o git diff pra ver a diferença
#guardar os trechos
#talvez em paralelo: rodar o pyan3 pra pegar o grafo de dependencias
#funcao pra correlacionar os trechos com o grafo de dependencias e achar testes afetados
#pega a nova lista de testes e manda para o ranker