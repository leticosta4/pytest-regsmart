from __future__ import annotations

import os
from dataclasses import dataclass

from .deps_graph import DependencyGraph, get_dependency_graph
from .git_manager import DiffResult, get_git_diff


@dataclass
class SelectionResult:
    affected_tests: list[str]
    has_diff: bool
    branch: str


def _is_test_file(filepath: str) -> bool:
    filename = os.path.basename(filepath)
    return filename.startswith("test_") or filename.endswith("_test.py")


def get_affected_tests(diff_result: DiffResult, deps_graph: DependencyGraph) -> list[str]:
    #for each file modified in the diff, look up its node in the dependency graph and get the related value (dependents)
    #loooking the dependents, keep only those that are tests (maybe via regex or file-name heuristic)
    #i also want indirectly affected tests, not just direct dependents
    
    changed_files = set(diff_result.modified_files) | set(diff_result.untracked_files)
    affected_tests = sorted(f for f in changed_files if _is_test_file(f))
    seen = set(changed_files)
    to_check = list(changed_files)

    while to_check:
        current_file = to_check.pop()
        dependents = deps_graph.dependents.get(current_file, set())
        
        for dependent in dependents:
            if dependent in seen:
                continue

            seen.add(dependent) #seen = dependent was discovered and will be visited
            to_check.append(dependent) #even if not a test, check its dependents for indirect affected tests

            if _is_test_file(dependent):
                affected_tests.append(dependent)

    return sorted(affected_tests)


def run_rts() -> SelectionResult:
    """[wip] Orchestrates the selection..."""

    diff_result = get_git_diff()
    deps_graph = get_dependency_graph()  # maybe parallelize this with the git diff later

    return SelectionResult(
        affected_tests=get_affected_tests(diff_result, deps_graph),
        has_diff=bool(diff_result.modified_files or diff_result.untracked_files),
        branch=diff_result.used_branch,
    )
