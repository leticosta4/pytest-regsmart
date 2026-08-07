from __future__ import annotations

import os
from pathlib import Path

from pytest import mark

from pytest_regsmart.selection.deps_graph import (
    DependencyGraph,
    _build_module_relative_path,
    _find_py_files,
    _invert_dependency_graph,
    get_dependency_graph,
)


def _write(tmp_path: Path, relpath: str, content: str = "") -> Path:
    filepath = tmp_path / relpath
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    return filepath


# ---------------------------------------------------------------------------
# _find_py_files
# ---------------------------------------------------------------------------


def test_find_py_files_only_discovers_project_files(tmp_path):
    _write(tmp_path, "app/mod.py")
    _write(tmp_path, "app/sub/helper.py")
    _write(tmp_path, "not_python.txt")

    files = _find_py_files(str(tmp_path))

    assert {os.path.relpath(f, tmp_path) for f in files} == {
        os.path.join("app", "mod.py"),
        os.path.join("app", "sub", "helper.py"),
    }


def test_find_py_files_excludes_env_and_build_dirs(tmp_path):
    _write(tmp_path, "app/mod.py")
    _write(tmp_path, ".venv/lib.py")
    _write(tmp_path, ".git/hooks.py")
    _write(tmp_path, "__pycache__/cache.py")
    _write(tmp_path, "dist/bundle.py")
    _write(tmp_path, "build/gen.py")
    _write(tmp_path, "pkg.egg-info/PKG-INFO.py")

    files = _find_py_files(str(tmp_path))

    assert {os.path.relpath(f, tmp_path) for f in files} == {
        os.path.join("app", "mod.py")
    }


# ---------------------------------------------------------------------------
# _build_module_relative_path
# ---------------------------------------------------------------------------


def test_build_module_relative_path(tmp_path):
    fullpaths = {
        "pkg.mod": str(tmp_path / "pkg" / "mod.py"),
        "pkg": str(tmp_path / "pkg" / "__init__.py"),
    }

    result = _build_module_relative_path(fullpaths, str(tmp_path))

    assert result == {
        "pkg.mod": os.path.join("pkg", "mod.py"),
        "pkg": os.path.join("pkg", "__init__.py"),
    }


# ---------------------------------------------------------------------------
# _invert_dependency_graph
# ---------------------------------------------------------------------------

@mark.parametrize(
    "module_imports,module_to_path,expected_dependents",
    [
        (
            {
                "app.main": {"app.service", "os"},
                "app.service": {"app.helpers"},
            },
            {
                "app.main": "app/main.py",
                "app.service": "app/service.py",
                "app.helpers": "app/helpers.py",
            },
            {
                "app/service.py": {"app/main.py"},
                "app/helpers.py": {"app/service.py"},
            },
        ),
        (
            {
                "app.main": {"app.service", "os", "requests"},
                "app.service": {"numpy"},
            },
            {
                "app.main": "app/main.py",
                "app.service": "app/service.py",
            },
            {
                "app/service.py": {"app/main.py"},
            },
        ),
        (
            {
                "app.main": {"app.service"},
                "app.service": set(),
            },
            {
                "app.main": "app/main.py",
                "app.service": "app/service.py",
            },
            {
                "app/service.py": {"app/main.py"},
            },
        ), 
    ])
def test_invert_dependency_graph_cases(module_imports,module_to_path,expected_dependents):
    graph = _invert_dependency_graph(module_imports, module_to_path)
    
    assert graph == DependencyGraph(dependents=expected_dependents)


# ---------------------------------------------------------------------------
# get_dependency_graph (end-to-end)
# ---------------------------------------------------------------------------


def _build_sample_project(repo):
    root = Path(repo.working_tree_dir)
    _write(root, "mypkg/__init__.py")
    _write(
        root,
        "mypkg/service.py",
        "import os\n\ndef run():\n    return os.getcwd()\n",
    )
    _write(root, "mypkg/main.py", "from .service import run\n")
    _write(root, "tests/test_app.py", "from mypkg.service import run\n")
    _write(root, ".venv/skip.py", "import os\n")
    _write(root, "build/gen.py", "print('generated')\n")


def test_get_dependency_graph_end_to_end(git_repo):
    _build_sample_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir)

    assert graph.dependents["mypkg/service.py"] == {
        "mypkg/main.py",
        "tests/test_app.py",
    }
    assert graph.dependents["mypkg/__init__.py"] == {
        "mypkg/main.py",
        "tests/test_app.py",
    }


def test_get_dependency_graph_drops_stdlib_and_non_repo_files(git_repo):
    _build_sample_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir)

    for filepath in graph.dependents:
        assert filepath.endswith(".py")
        assert not any(
            part in filepath
            for part in (".venv", "build", "__pycache__", ".git")
        )
    assert not any("os" in filepath for filepath in graph.dependents)


def test_get_dependency_graph_leaf_module_has_no_entry(git_repo):
    _build_sample_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir)

    assert "mypkg/main.py" not in graph.dependents
    assert "tests/test_app.py" not in graph.dependents


def test_get_dependency_graph_defaults_to_dot_repo(monkeypatch, git_repo):
    _build_sample_project(git_repo)
    monkeypatch.setattr(
        "pytest_regsmart.selection.deps_graph.resolve_repo", lambda repo_path=".": git_repo
    )

    graph = get_dependency_graph()

    assert graph.dependents["mypkg/service.py"] == {
        "mypkg/main.py",
        "tests/test_app.py",
    }
