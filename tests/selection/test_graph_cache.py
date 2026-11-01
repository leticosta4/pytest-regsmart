from __future__ import annotations

import os
import time

import pytest

from pytest_regsmart.const import DIFF_LEVEL
from pytest_regsmart.selection import graph_cache
from pytest_regsmart.selection.models import DependencyGraph


def _graph(value: str = "node") -> DependencyGraph:
    return DependencyGraph(dependents={value: {"test"}})


def test_miss_then_hit_and_roundtrip(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("value = 1\n")
    calls = []

    def build():
        calls.append(1)
        return _graph()

    first, status = graph_cache.get_or_build(
        str(tmp_path / "cache"), DIFF_LEVEL.FILE, str(tmp_path), [str(source)], build
    )
    second, hit_status = graph_cache.get_or_build(
        str(tmp_path / "cache"),
        DIFF_LEVEL.FILE,
        str(tmp_path),
        [str(source)],
        lambda: pytest.fail("cache should hit"),
    )
    assert status == "miss"
    assert hit_status == "hit"
    assert first == second
    assert len(calls) == 1


def test_content_change_invalidates_cache(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("value = 1\n")
    cache_dir = str(tmp_path / "cache")
    graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(source)], _graph
    )
    source.write_text("value = 2\n")
    _, status = graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(source)], _graph
    )
    assert status == "miss"


def test_file_set_and_level_are_part_of_cache_key(tmp_path):
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("a = 1\n")
    second.write_text("b = 1\n")
    cache_dir = str(tmp_path / "cache")
    graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(first)], _graph
    )
    _, changed_files = graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(first), str(second)], _graph
    )
    _, changed_level = graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FUNCTION, str(tmp_path), [str(first)], _graph
    )
    assert changed_files == changed_level == "miss"


def test_branch_contents_can_be_reused_and_pruned(tmp_path):
    source = tmp_path / "module.py"
    cache_dir = str(tmp_path / "cache")
    source.write_text("value = 'a'\n")
    graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(source)], _graph
    )
    source.write_text("value = 'b'\n")
    graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(source)], _graph
    )
    source.write_text("value = 'a'\n")
    _, status = graph_cache.get_or_build(
        cache_dir,
        DIFF_LEVEL.FILE,
        str(tmp_path),
        [str(source)],
        lambda: pytest.fail("old content should be retained"),
    )
    assert status == "hit"
    for index in range(6):
        source.write_text(f"value = {index}\n")
        graph_cache.get_or_build(
            cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(source)], _graph
        )
    assert (
        len(list((tmp_path / "cache").glob("graph-file-*.pkl")))
        <= graph_cache._MAX_ENTRIES
    )


def test_corrupt_payload_is_rebuilt(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("value = 1\n")
    cache_dir = str(tmp_path / "cache")
    fingerprint = graph_cache.compute_fingerprint(
        str(tmp_path), [str(source)], DIFF_LEVEL.FILE
    )
    path, _ = graph_cache._paths(cache_dir, DIFF_LEVEL.FILE, fingerprint)
    path.parent.mkdir()
    path.write_bytes(b"not a pickle")
    result, status = graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(source)], _graph
    )
    assert result == _graph()
    assert status == "miss"


def test_builder_failure_does_not_save_and_releases_lock(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("value = 1\n")
    cache_dir = str(tmp_path / "cache")

    def fail():
        raise ValueError("build failed")

    with pytest.raises(ValueError):
        graph_cache.get_or_build(
            cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(source)], fail
        )
    assert not list((tmp_path / "cache").glob("*.pkl"))
    assert not list((tmp_path / "cache").glob("*.lock"))


def test_disabled_cache_always_builds(tmp_path):
    calls = []

    def build():
        calls.append(1)
        return _graph()

    for _ in range(2):
        graph, status = graph_cache.get_or_build(
            None, DIFF_LEVEL.FILE, str(tmp_path), [], build
        )
        assert graph == _graph()
        assert status == "disabled"
    assert len(calls) == 2


def test_unreadable_cache_write_does_not_break_build(tmp_path, monkeypatch):
    source = tmp_path / "module.py"
    source.write_text("value = 1\n")
    cache_dir = str(tmp_path / "cache")
    monkeypatch.setattr(
        graph_cache.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("no"))
    )
    graph, status = graph_cache.get_or_build(
        cache_dir, DIFF_LEVEL.FILE, str(tmp_path), [str(source)], _graph
    )
    assert graph == _graph()
    assert status == "miss"


def test_waiter_loads_graph_written_by_lock_owner(tmp_path, monkeypatch):
    source = tmp_path / "module.py"
    source.write_text("value = 1\n")
    cache_dir = tmp_path / "cache"
    fingerprint = graph_cache.compute_fingerprint(str(tmp_path), [str(source)], DIFF_LEVEL.FILE)
    _, lock = graph_cache._paths(str(cache_dir), DIFF_LEVEL.FILE, fingerprint)
    lock.parent.mkdir()
    lock.touch()
    attempts = iter([None, _graph()])
    monkeypatch.setattr(graph_cache, "load", lambda *args: next(attempts))
    monkeypatch.setattr(graph_cache.time, "sleep", lambda _: None)

    graph, status = graph_cache.get_or_build(
        str(cache_dir), DIFF_LEVEL.FILE, str(tmp_path), [str(source)],
        lambda: pytest.fail("a waiter should use the owner's graph"),
    )
    assert graph == _graph()
    assert status == "waited"


def test_orphaned_lock_is_removed(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("value = 1\n")
    cache_dir = tmp_path / "cache"
    fingerprint = graph_cache.compute_fingerprint(str(tmp_path), [str(source)], DIFF_LEVEL.FILE)
    _, lock = graph_cache._paths(str(cache_dir), DIFF_LEVEL.FILE, fingerprint)
    lock.parent.mkdir()
    lock.touch()
    old = time.time() - graph_cache._LOCK_TIMEOUT - 1
    os.utime(lock, (old, old))

    graph, status = graph_cache.get_or_build(
        str(cache_dir), DIFF_LEVEL.FILE, str(tmp_path), [str(source)], _graph
    )
    assert graph == _graph()
    assert status == "miss"
    assert not lock.exists()
