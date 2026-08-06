from __future__ import annotations

import os

from .deps_graph import DependencyGraph, get_dependency_graph
from .git_manager import DiffResult, get_git_diff


def _is_test_file(filepath: str) -> bool:
    filename = os.path.basename(filepath)
    return filename.startswith("test_") or filename.endswith("_test.py")


def get_affected_tests(diff_result: DiffResult, deps_graph: DependencyGraph) -> list[str]:
    #para cada arquivo modificado no diff vai procurar a ref dele no grafo de dependencia e checar o valor relacioando (dependentes)
    #dentro dos dependentes vai filtrar só os que são testes (talvez por regex ou por heuristica de nome de arquivo)
    #eu quero pegar testes imapctados indiretamente tb, nao é só o dependente direto
    
    changed_files = set(diff_result.modified_files) | set(diff_result.untracked_files)
    seen = set(changed_files)
    to_check = list(changed_files)
    affected_tests = []

    while to_check:
        current_file = to_check.pop()
        dependents = deps_graph.dependents.get(current_file, set())
        
        for dependent in dependents:
            if dependent in seen:
                continue

            seen.add(dependent) #seen = o dependente foi descoberto, mas ainda sera visitadoe e
            to_check.append(dependent) #caso nao seja um teste ainda quero checar os dependentes pra ver o que pode estar sendo afetado indiretamente

            if _is_test_file(dependent):
                affected_tests.append(dependent)

    return sorted(affected_tests)


def run_rts() -> list[str]:
    """[wip] Orquestra a seleção..."""

    diff_result = get_git_diff()
    deps_graph = get_dependency_graph() #talvez vou paralelizar isso com o git diff mais pra frente

    return get_affected_tests(diff_result, deps_graph)
