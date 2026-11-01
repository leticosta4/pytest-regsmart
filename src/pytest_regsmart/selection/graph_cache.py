"""Content-addressed cache for pyan dependency graphs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import logging
import os
import pickle
import sys
import tempfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from pytest_regsmart.const import DIFF_LEVEL

from .models import DependencyGraph

_CACHE_FORMAT = 1
_MAX_ENTRIES = 4
_logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def plugin_code_digest() -> str:
    digest = hashlib.sha256()
    package = Path(__import__("pytest_regsmart").__file__).parent
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()


def compute_fingerprint(working_dir: str, files: list[str], level: DIFF_LEVEL) -> str:
    digest = hashlib.sha256()
    parts = (
        str(_CACHE_FORMAT),
        plugin_code_digest(),
        level.value,
        importlib.metadata.version("pyan3"),
        f"{sys.version_info.major}.{sys.version_info.minor}",
    )
    for part in parts:
        digest.update(part.encode())
        digest.update(b"\0")
    for filename in sorted(files, key=lambda f: os.path.relpath(f, working_dir)):
        path = Path(filename)
        relpath = os.path.relpath(filename, working_dir).replace(os.sep, "/")
        digest.update(relpath.encode())
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()


def _paths(cache_dir: str, level: DIFF_LEVEL, fingerprint: str) -> tuple[Path, Path]:
    stem = f"graph-{level.value}-{fingerprint[:16]}"
    return Path(cache_dir) / f"{stem}.pkl", Path(cache_dir) / f"{stem}.lock"


def load(cache_dir: str, level: DIFF_LEVEL, fingerprint: str) -> DependencyGraph | None:
    try:
        path, _ = _paths(cache_dir, level, fingerprint)
        with path.open("rb") as stream:
            payload = pickle.load(stream)
        if (
            payload.get("format") == _CACHE_FORMAT
            and payload.get("fingerprint") == fingerprint
            and payload.get("level") == level.value
            and isinstance(payload.get("graph"), DependencyGraph)
        ):
            return payload["graph"]
    except Exception as exc:  # noqa: BLE001 - corrupt or incompatible entries are misses
        _logger.debug("dependency graph cache load miss: %s", exc)
    return None


def _prune(cache_dir: str, level: DIFF_LEVEL) -> None:
    entries = sorted(
        Path(cache_dir).glob(f"graph-{level.value}-*.pkl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in entries[_MAX_ENTRIES:]:
        try:
            path.unlink()
        except OSError:
            pass


def save(
    cache_dir: str, level: DIFF_LEVEL, fingerprint: str, graph: DependencyGraph
) -> None:
    temp_name = None
    try:
        directory = Path(cache_dir)
        directory.mkdir(parents=True, exist_ok=True)
        gitignore = directory / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")
        path, _ = _paths(cache_dir, level, fingerprint)
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix="graph-", suffix=".tmp", delete=False
        ) as stream:
            temp_name = stream.name
            pickle.dump(
                {
                    "format": _CACHE_FORMAT,
                    "fingerprint": fingerprint,
                    "level": level.value,
                    "graph": graph,
                },
                stream,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        os.replace(temp_name, path)
        _prune(cache_dir, level)
    except Exception as exc:  # noqa: BLE001 - cache failures must not affect pytest
        _logger.warning("regsmart: could not save dependency graph cache: %s", exc)
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def get_or_build(
    cache_dir: str | None,
    level: DIFF_LEVEL,
    working_dir: str,
    files: list[str],
    build: Callable[[], DependencyGraph],
) -> tuple[DependencyGraph, str]:
    if cache_dir is None:
        return build(), "disabled"
    try:
        fingerprint = compute_fingerprint(working_dir, files, level)
        directory = Path(cache_dir)
        directory.mkdir(parents=True, exist_ok=True)
        cached = load(cache_dir, level, fingerprint)
    except Exception as exc:  # noqa: BLE001 - cache failures must not affect pytest
        _logger.debug(
            "dependency graph cache unavailable; building without cache: %s", exc
        )
        return build(), "disabled"
    if cached is not None:
        return cached, "hit"
    graph = build()
    save(cache_dir, level, fingerprint, graph)
    return graph, "miss"
