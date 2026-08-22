from __future__ import annotations

import os
from dataclasses import dataclass

from pytest_regsmart.const import DEFAULT_DIFF_LEVEL, DIFF_LEVEL

from ..utils import _is_test_file
from .deps_graph import DependencyGraph, get_dependency_graph
from .git_manager import DiffResult, get_git_diff


@dataclass
class SelectionResult:
    affected_tests: list[str]
    has_diff: bool
    branch: str


def line_diff_match_function_ids(
    diff_result: DiffResult,
    deps_graph: DependencyGraph,
) -> set[str]:
    """Project changed diff lines onto function-level call graph nodes.
    Hunks outside every function (imports, constants) or files without 
    specific range (untracked, sem entrada em changed_line_ranges) caem
    de volta para "todas as funções do arquivo" como aproximação conservadora.
    """
    changed: set[str] = set()

    no_range_files = (
        set(diff_result.untracked_files)
        | (set(diff_result.modified_files) - set(diff_result.changed_line_ranges))
    ) #checar se isso realmente funciona

    for filepath in no_range_files:
        changed.update(deps_graph.functions_by_file.get(filepath, set()))

    for filepath, ranges in diff_result.changed_line_ranges.items():
        candidates = deps_graph.functions_by_file.get(filepath, set())
        if not candidates:
            continue

        for start, end in ranges:
            matched = {
                fid for fid in candidates
                if start <= deps_graph.function_nodes[fid].end_line
                and deps_graph.function_nodes[fid].start_line <= end
            }
            changed.update(matched or candidates)  # sem match preciso -> conservador

    return changed


def _get_affected_nodes(
    changed_nodes: set[str],
    deps_graph: DependencyGraph,
) -> set[str]:
    """ For each file/function modified in the diff, look up its node in the dependency graph and get the related value (dependents)
    #loooking the dependents, keep only those that are tests 
    #i also want indirectly affected tests, not just direct dependents"""

    seen = set(changed_nodes)
    to_check = list(changed_nodes)

    while to_check:
        current_node = to_check.pop()
        dependents = deps_graph.dependents.get(current_node, set())

        for dependent in dependents:
            if dependent in seen:
                continue

            seen.add(dependent)  #seen = dependent was discovered and will be visited
            to_check.append(dependent)  #even if not a test, check its dependents for indirect affected tests

    return seen


def _get_affected_tests_at_file_level(
    diff_result: DiffResult,
    deps_graph: DependencyGraph,
) -> list[str]:
    changed_files = set(diff_result.modified_files) | set(diff_result.untracked_files)
    affected_nodes = _get_affected_nodes(changed_files, deps_graph)

    return sorted(node for node in affected_nodes if _is_test_file(node))


def _get_affected_tests_at_function_level(
    diff_result: DiffResult,
    deps_graph: DependencyGraph,
) -> list[str]:
    changed_function_ids = line_diff_match_function_ids(diff_result, deps_graph)
    affected_function_ids = _get_affected_nodes(changed_function_ids, deps_graph)

    # pytest filters collected items by their nodeid. A function graph id uses
    # dotted Python names, while pytest uses ``path.py::Class::test``.
    return sorted(
        {
            _function_id_to_pytest_nodeid(
                function_id, deps_graph.function_nodes[function_id].filepath
            )
            for function_id in affected_function_ids
            if _is_test_file(deps_graph.function_nodes[function_id].filepath)
        }
    )


def _function_id_to_pytest_nodeid(function_id: str, filepath: str) -> str:
    """Translate a pyan3 function id into the equivalent pytest nodeid.
    
    tests.selection.test_selector.py.test_regsmart_requires_git_repo =>>
    tests/selection/test_selector.py::test_regsmart_requires_git_repo
    """


    module_name = os.path.splitext(filepath)[0].replace(os.sep, ".")
    qualified_name = function_id.removeprefix(f"{module_name}.")

    return f"{filepath}::{qualified_name.replace('.', '::')}"


def run_rts(level: DIFF_LEVEL = DEFAULT_DIFF_LEVEL) -> SelectionResult:
    """[wip] Orchestrates the selection..."""

    diff_result = get_git_diff(diff_level= level)
    deps_graph = get_dependency_graph(graph_level= level)  # maybe parallelize this with the git diff later

    selected = (
        _get_affected_tests_at_function_level(diff_result, deps_graph)
        if level == DIFF_LEVEL.FUNCTION
        else _get_affected_tests_at_file_level(diff_result, deps_graph)
    )
    
    return SelectionResult(
        affected_tests=selected,
        has_diff=bool(diff_result.modified_files or diff_result.untracked_files),
        branch=diff_result.used_branch,
    )
