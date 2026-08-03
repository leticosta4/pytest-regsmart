from __future__ import annotations

from .deps_graph import DependencyGraph, get_dependency_graph
from .git_diff import DiffResult, get_git_diff


def get_affected_tests(diff_result: DiffResult, imports_deps_graph: DependencyGraph) -> list[str]:
    #para cada arquivo modificado no diff vai procurar a ref dele no grafo de dependencia e checar o valor relacioando (dependentes)
    #dentro dos dependentes vai filtrar só os que são testes (talvez por regex ou por heuristica de nome de arquivo)
    #eu quero pegar testes imapctados indiretamente tb, nao é só o dependente direto
    pass


def run_rts():
    """[wip] Orquestra a seleção..."""

    diff_result = get_git_diff()  # noqa: F841
    imports_deps_graph = get_dependency_graph()  # noqa: F841  #talvez vou paralelizar isso com o git diff mais pra frente

    selected_tests = get_affected_tests(diff_result, imports_deps_graph)  # noqa: F841


#rodar o git diff pra ver a diferença
#guardar os trechos
#talvez em paralelo: rodar o pyan3 pra pegar o grafo de dependencias
#funcao pra correlacionar os trechos com o grafo de dependencias e achar testes afetados
#pega a nova lista de testes e manda para o ranker