from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

from pytest_regsmart.const import (
    DEFAULT_DIFF_LEVEL,
    DEFAULT_DIFF_SOURCE,
    DIFF_LEVEL,
    DIFF_SOURCE,
)

from ..utils import _filter_python_files, _is_conftest, _is_test_file
from .deps_graph import get_dependency_graph
from .git_manager import get_git_diff
from .models import DependencyGraph, DiffResult

SELECTION_TIME_KEY = "Time to run the regression test selection (s)"
SELECTION_TIME_KEY_FILE_LEVEL = "Time to run the file-level regression test selection (s)"


def _files_without_line_ranges(diff_result: DiffResult) -> set[str]:
    return (
        set(diff_result.untracked_files)
        | (set(diff_result.modified_files) - set(diff_result.changed_line_ranges))
        | set(diff_result.deleted_files)
    )


@dataclass
class SelectionResult:
    affected_tests: list[str]
    has_diff: bool
    branch: str
    full_run: bool = False
    no_merge_base: bool = False
    level: DIFF_LEVEL = DEFAULT_DIFF_LEVEL
    degraded_to_file: bool = False
    deleted_files: list[str] = field(default_factory=list)
    unresolved_files: list[str] = field(default_factory=list)
    degraded_from_unresolved: bool = False


def line_diff_match_function_ids(
    diff_result: DiffResult,
    deps_graph: DependencyGraph,
) -> set[str]:
    """Project changed diff lines onto function-level call graph nodes.
    Hunks outside every function (imports, constants) or files without 
    specific range fallback to the entire file"""
    changed: set[str] = set()

    for filepath in _files_without_line_ranges(diff_result):
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
            changed.update(matched or candidates)  #not a specific match

    return changed


def _unresolved_changed_files(
    diff_result: DiffResult,
    deps_graph: DependencyGraph,
) -> set[str]:
    """Changed files the function-level graph cannot fully resolve.

    A file is unresolved when it has no function node in the graph (e.g. a
    module of constants, or a deleted file) or when some changed hunk falls
    outside every function/method/class: the node that used to exist may be
    gone (deleted function) or the change is not tied to any callable
    (imports, constants, comments). Such files are handled conservatively at
    the file level, since function-level dependents cannot be located."""
 
    unresolved: set[str] = set()

    for filepath in _files_without_line_ranges(diff_result):
        if not deps_graph.functions_by_file.get(filepath):
            unresolved.add(filepath)

    unresolved.update(diff_result.pure_deletion_files)

    for filepath, ranges in diff_result.changed_line_ranges.items():
        candidates = deps_graph.functions_by_file.get(filepath, set())
        if not candidates:
            unresolved.add(filepath)
            continue

        for start, end in ranges:
            matched = any(
                start <= deps_graph.function_nodes[fid].end_line
                and deps_graph.function_nodes[fid].start_line <= end
                for fid in candidates
            )
            if not matched:
                unresolved.add(filepath)
                break

    return unresolved


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


def _add_collected_fixture_edges(items: list, deps_graph: DependencyGraph) -> None:
    """Connect pytest's resolved fixture closure to its collected test item.

    Pytest has already resolved overrides, autouse fixtures and parametrized
    fixture definitions by collection time; use that exact closure instead of
    trying to infer fixture names or types from test annotations.
    """
    by_location: dict[tuple[str, str], set[str]] = {}
    by_name: dict[str, list[tuple[str, str]]] = {}
    for function_id, metadata in deps_graph.function_nodes.items():
        name = function_id.rsplit(".", 1)[-1]
        by_location.setdefault((os.path.normpath(metadata.filepath), name), set()).add(function_id)
        by_name.setdefault(name, []).append((function_id, metadata.filepath))

    # Parametrized variants and tests of the same file share these lookups:
    # resolve each (test file, test name) and each fixture function once.
    test_ids_cache: dict[tuple[str, str], set[str]] = {}
    fixture_ids_cache: dict[tuple[str, str], set[str]] = {}
    cwd = os.getcwd()

    for item in items:
        test_path = os.path.normpath(str(item.path))
        test_name = item.nodeid.split("::")[-1].split("[")[0]
        test_key = (test_path, test_name)
        test_ids = test_ids_cache.get(test_key)
        if test_ids is None:
            test_ids = by_location.get(test_key, set())
            if not test_ids:
                # Graph paths are relative to the repository; pytest paths may be
                # absolute. Match by suffix while retaining the function name.
                basename = test_path.replace(os.sep, "/").split("/")[-1]
                test_ids = {
                    fid for fid, filepath in by_name.get(test_name, ())
                    if filepath.endswith(basename)
                }
            test_ids_cache[test_key] = test_ids
        if not test_ids:
            continue
        fixtureinfo = getattr(item, "_fixtureinfo", None)
        definitions = getattr(fixtureinfo, "name2fixturedefs", {}) or {}
        fixture_functions = set()
        for fixturedefs in definitions.values():
            for fixturedef in fixturedefs or ():
                func = getattr(fixturedef, "func", None)
                if func is None:
                    continue
                code = getattr(func, "__code__", None)
                if code is None:
                    continue
                fixture_key = (code.co_filename, func.__name__)
                fixture_ids = fixture_ids_cache.get(fixture_key)
                if fixture_ids is None:
                    try:
                        fixture_path = os.path.relpath(code.co_filename, cwd)
                    except ValueError:
                        fixture_ids = set()
                    else:
                        fixture_ids = by_location.get(
                            (os.path.normpath(fixture_path), func.__name__), set()
                        )
                    fixture_ids_cache[fixture_key] = fixture_ids
                fixture_functions.update(fixture_ids)
        for fixture_id in fixture_functions:
            deps_graph.dependents.setdefault(fixture_id, set()).update(test_ids)


def _get_affected_tests_at_file_level(
    diff_result: DiffResult,
    deps_graph: DependencyGraph,
    changed_files: set[str] | None = None,
) -> list[str]:
    if changed_files is None:
        changed_files = (
            set(diff_result.modified_files)
            | set(diff_result.untracked_files)
            | set(diff_result.deleted_files)
        )
    affected_nodes = _get_affected_nodes(changed_files, deps_graph)

    return sorted(node for node in affected_nodes if _is_test_file(node))


def _get_affected_tests_at_function_level(
    diff_result: DiffResult,
    deps_graph: DependencyGraph,
) -> list[str]:
    changed_function_ids = line_diff_match_function_ids(diff_result, deps_graph)
    affected_function_ids = _get_affected_nodes(changed_function_ids, deps_graph)
    # Parent-side static analysis cannot observe code executed by a nested
    # pytest collection. Keep such tests as a conservative fallback so changes
    # to fixtures, hooks, or plugin behavior used only in the child are covered.
    affected_function_ids.update(deps_graph.subprocess_tests)

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


_NODEID_BOUNDARY = re.compile(r"\[|::")


def _nodeid_candidates(nodeid: str):
    """Yield ``nodeid`` and each prefix that ends right before ``[`` or ``::``.

    A selected node matches an item when it equals the item's nodeid or when
    the nodeid starts with the selected node followed by ``[`` (parametrized
    variant) or ``::`` (member of a selected class/module). Those are exactly
    the prefixes yielded here, so a set lookup per candidate replaces the
    comparison against every selected node.
    """
    yield nodeid
    for boundary in _NODEID_BOUNDARY.finditer(nodeid):
        yield nodeid[: boundary.start()]


def _matches_function_selection(nodeid: str, selected_nodes: set[str]) -> bool:
    return any(
        candidate in selected_nodes for candidate in _nodeid_candidates(nodeid)
    )


def filter_pytest_items_for_rtp(items: list, selected_nodes: set[str], diff_level) -> None:
    # ``item.nodeid`` is read once per item; the selection is looked up in a set
    # instead of being scanned for every item (O(items x selected) before).
    if not isinstance(selected_nodes, (set, frozenset)):
        selected_nodes = set(selected_nodes)
    if diff_level == DIFF_LEVEL.FILE:
        items[:] = [
            item for item in items if item.nodeid.split("::")[0] in selected_nodes
        ]
        return
    items[:] = [
        item
        for item in items
        if _matches_function_selection(item.nodeid, selected_nodes)
    ]


def run_rts(
    level: DIFF_LEVEL = DEFAULT_DIFF_LEVEL,
    log_dict: dict | None = None,
    time_key: str = SELECTION_TIME_KEY,
    diff_source: DIFF_SOURCE = DEFAULT_DIFF_SOURCE,
    items: list | None = None,
    files_to_select: set[str] | None = None,
) -> SelectionResult:
    """Orchestrates the selection..."""
    start_time = time.time()

    diff_result = get_git_diff(diff_level=level, diff_source=diff_source)
    diff_result.modified_files = _filter_python_files(diff_result.modified_files)
    diff_result.untracked_files = _filter_python_files(diff_result.untracked_files)
    diff_result.deleted_files = _filter_python_files(diff_result.deleted_files)
    has_diff = bool(
        diff_result.modified_files
        or diff_result.untracked_files
        or diff_result.deleted_files
    )
    used_branch = diff_result.used_branch

    if diff_result.no_merge_base:
        return SelectionResult(
            affected_tests=[],
            has_diff=has_diff,
            branch=used_branch,
            no_merge_base=True,
            level=level,
        )

    if not has_diff:
        return SelectionResult(
            affected_tests=[],
            has_diff=has_diff,
            branch=used_branch,
            level=level,
        )

    changed_files = (
        set(diff_result.modified_files)
        | set(diff_result.untracked_files)
        | set(diff_result.deleted_files)
    )
    if any(_is_conftest(f) for f in changed_files):
        return SelectionResult(
            affected_tests=[],
            has_diff=has_diff,
            branch=used_branch,
            full_run=True,
            level=level,
        )
    
    deps_graph = get_dependency_graph(
        graph_level=level,
        deleted_files=diff_result.deleted_files,
    )
    if level == DIFF_LEVEL.FUNCTION and items:
        _add_collected_fixture_edges(items, deps_graph)

    selected = (
        _get_affected_tests_at_function_level(diff_result, deps_graph)
        if level == DIFF_LEVEL.FUNCTION
        else _get_affected_tests_at_file_level(
            diff_result, deps_graph, changed_files=files_to_select
        )
    )

    unresolved = (
        sorted(_unresolved_changed_files(diff_result, deps_graph))
        if level == DIFF_LEVEL.FUNCTION
        else []
    )

    if log_dict is not None:
        log_dict[time_key] = time.time() - start_time

    return SelectionResult(
        affected_tests=selected,
        has_diff=has_diff,
        branch=used_branch,
        level=level,
        deleted_files=diff_result.deleted_files,
        unresolved_files=unresolved,
    )


def _should_degrade_to_file(result: SelectionResult, level: DIFF_LEVEL) -> bool:
    return (
        level == DIFF_LEVEL.FUNCTION
        and result.has_diff
        and not result.full_run
        and not result.no_merge_base
        and (not result.affected_tests or bool(result.unresolved_files))
    )


def run_rts_with_fallback(
    level: DIFF_LEVEL = DEFAULT_DIFF_LEVEL,
    log_dict: dict | None = None,
    diff_source: DIFF_SOURCE = DEFAULT_DIFF_SOURCE,
    items: list | None = None,
) -> SelectionResult:
    """Run RTS and, on a suspicious function-level result, retry at file level.

    An empty function-level selection falls back to file-level selection. When
    it found tests but some changed files are unresolved, add file-level
    dependents for only those files and preserve the function-level results.
    """
    run_kwargs = {
        "level": level,
        "log_dict": log_dict,
        "diff_source": diff_source,
    }
    if items is not None:
        run_kwargs["items"] = items
    result = run_rts(**run_kwargs)

    if not _should_degrade_to_file(result, level):
        return result

    fallback_kwargs = {
        "level": DIFF_LEVEL.FILE,
        "log_dict": log_dict,
        "time_key": SELECTION_TIME_KEY_FILE_LEVEL,
        "diff_source": diff_source,
    }
    if items is not None:
        fallback_kwargs["items"] = items

    if not result.affected_tests:
        fallback = run_rts(**fallback_kwargs)
        fallback.degraded_to_file = True
        fallback.degraded_from_unresolved = bool(result.unresolved_files)
        fallback.unresolved_files = result.unresolved_files
        return fallback

    if result.unresolved_files:
        file_level = run_rts(
            **fallback_kwargs,
            files_to_select=set(result.unresolved_files),
        )
        result.affected_tests = sorted(
            set(result.affected_tests) | set(file_level.affected_tests)
        )
        result.degraded_to_file = True
        result.degraded_from_unresolved = True
    return result
