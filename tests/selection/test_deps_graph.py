from __future__ import annotations

import logging
import os
from pathlib import Path

from pyan.analyzer import CallGraphVisitor
from pytest import mark, param, raises

from pytest_regsmart.const import DIFF_LEVEL
from src.pytest_regsmart.selection import deps_graph
from src.pytest_regsmart.selection.deps_graph import (
    DependencyGraph,
    FunctionMetadata,
    _build_import_name_to_path,
    _convert_module_to_relative_path,
    _extract_function_nodes,
    _find_py_files,
    _invert_dependency_map,
    _readable_python_files,
    get_dependency_graph,
)

_LATIN1_BYTES = b"# -*- coding: latin-1 -*-\nNAME = 'caf\xe9'\n"
_PY2_SOURCE = 'print "legacy code"\n'


def _write(tmp_path: Path, relpath: str, content: str = "") -> Path:
    filepath = tmp_path / relpath
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    return filepath


def _write_bytes(tmp_path: Path, relpath: str, content: bytes) -> Path:
    filepath = tmp_path / relpath
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_bytes(content)
    return filepath


def _unparseable_files(repo, count: int) -> list[Path]:
    root = Path(repo.working_tree_dir)
    return [
        _write(root, f"legacy_{index}.py", f"print 'legacy {index}'\n")
        for index in range(count)
    ]


def _raiser(exc: Exception):
    def _build(*args, **kwargs):
        raise exc

    return _build


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
# _convert_module_to_relative_path
# ---------------------------------------------------------------------------


def test_convert_module_to_relative_path(tmp_path):
    fullpaths = {
        "pkg.mod": str(tmp_path / "pkg" / "mod.py"),
        "pkg": str(tmp_path / "pkg" / "__init__.py"),
    }

    result = _convert_module_to_relative_path(fullpaths, str(tmp_path))

    assert result == {
        "pkg.mod": os.path.join("pkg", "mod.py"),
        "pkg": os.path.join("pkg", "__init__.py"),
    }


# ---------------------------------------------------------------------------
# _build_import_name_to_path
# ---------------------------------------------------------------------------


@mark.parametrize(
    "fullpaths,expected",
    [
        param(
            {
                "pkg.__init__": "pkg/__init__.py",
                "pkg.service": "pkg/service.py",
                "tests.test_app": "tests/test_app.py",
            },
            {
                "pkg": os.path.join("pkg", "__init__.py"),
                "service": os.path.join("pkg", "service.py"),
                "test_app": os.path.join("tests", "test_app.py"),
                "pkg.service": os.path.join("pkg", "service.py"),
                "tests.test_app": os.path.join("tests", "test_app.py"),
            },
            id="flat-layout",
        ),
        param(
            {
                "src.hi": "src/hi.py",
                "src.text_toolkit.__init__": "src/text_toolkit/__init__.py",
                "src.text_toolkit.text_stats": "src/text_toolkit/text_stats.py",
                "tests.test_hi": "tests/test_hi.py",
                "tests.test_text_stats": "tests/test_text_stats.py",
            },
            {
                "hi": os.path.join("src", "hi.py"),
                "text_toolkit": os.path.join("src", "text_toolkit", "__init__.py"),
                "text_stats": os.path.join("src", "text_toolkit", "text_stats.py"),
                "test_hi": os.path.join("tests", "test_hi.py"),
                "test_text_stats": os.path.join("tests", "test_text_stats.py"),
                "src.hi": os.path.join("src", "hi.py"),
                "src.text_toolkit": os.path.join("src", "text_toolkit", "__init__.py"),
                "src.text_toolkit.text_stats": os.path.join("src", "text_toolkit", "text_stats.py"),
                "tests.test_hi": os.path.join("tests", "test_hi.py"),
                "tests.test_text_stats": os.path.join("tests", "test_text_stats.py"),
                "text_toolkit.text_stats": os.path.join("src", "text_toolkit", "text_stats.py"),
            },
            id="src-layout",
        ),
    ],
)
def test_build_import_name_to_path(tmp_path, fullpaths, expected):
    abs_fullpaths = {k: str(tmp_path / v) for k, v in fullpaths.items()}

    result = _build_import_name_to_path(abs_fullpaths, str(tmp_path))

    assert result == expected


def test_build_import_name_to_path_drops_ambiguous(tmp_path):
    fullpaths = {
        "a.foo": str(tmp_path / "a" / "foo.py"),
        "b.foo": str(tmp_path / "b" / "foo.py"),
    }

    result = _build_import_name_to_path(fullpaths, str(tmp_path))

    assert "foo" not in result


def test_build_import_name_to_path_init_package_name(tmp_path):
    fullpaths = {
        "mypkg.__init__": str(tmp_path / "mypkg" / "__init__.py"),
    }

    result = _build_import_name_to_path(fullpaths, str(tmp_path))

    assert result["mypkg"] == os.path.join("mypkg", "__init__.py")
    assert "__init__" not in result


# ---------------------------------------------------------------------------
# _invert_dependency_map
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
        (
            {
                "a.f": {"b.g", "c.h"},
                "b.g": {"c.h"},
            },
            None,
            {
                "b.g": {"a.f"},
                "c.h": {"a.f", "b.g"},
            },
        ), 
    ])
def test_invert_dependency_map_cases(module_imports,module_to_path,expected_dependents):
    graph = _invert_dependency_map(module_imports, module_to_path)
    
    assert graph == expected_dependents


@mark.parametrize(
    "connections,module_to_path,import_name_to_path,expected",
    [
        param(
            {"tests.test_app": {"text_toolkit"}},
            {
                "tests.test_app": "tests/test_app.py",
                "src.text_toolkit.__init__": "src/text_toolkit/__init__.py",
            },
            {"text_toolkit": "src/text_toolkit/__init__.py"},
            {"src/text_toolkit/__init__.py": {"tests/test_app.py"}},
            id="fallback-resolves",
        ),
        param(
            {"tests.test_app": {"mypkg.service"}},
            {
                "tests.test_app": "tests/test_app.py",
                "mypkg.service": "mypkg/service.py",
            },
            {"service": "mypkg/service.py"},
            {"mypkg/service.py": {"tests/test_app.py"}},
            id="exact-match-wins",
        ),
        param(
            {"tests.test_app": {"stdlib_module"}},
            {"tests.test_app": "tests/test_app.py"},
            {},
            {},
            id="fallback-also-fails",
        ),
    ],
)
def test_invert_dependency_map_fallback(connections, module_to_path, import_name_to_path, expected):
    result = _invert_dependency_map(connections, module_to_path, import_name_to_path)
    assert result == expected


# ---------------------------------------------------------------------------
# _extract_function_nodes
# ---------------------------------------------------------------------------


def test_extract_function_nodes_keeps_classes_and_methods(tmp_path):
    _write(tmp_path, "pkg/__init__.py")
    _write(
        tmp_path,
        "pkg/mod.py",
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n"
        "\n"
        "def make_calc():\n"
        "    return Calculator()\n",
    )

    graph = CallGraphVisitor(
        filenames=[str(tmp_path / "pkg" / "mod.py")],
        root=str(tmp_path),
        logger=logging.getLogger(__name__),
    )
    nodes, functions_by_file = _extract_function_nodes(graph, str(tmp_path))

    assert set(nodes) == {
        "pkg.mod.Calculator",
        "pkg.mod.Calculator.add",
        "pkg.mod.make_calc",
    }
    assert nodes["pkg.mod.Calculator.add"] == FunctionMetadata(
        filepath=os.path.join("pkg", "mod.py"),
        start_line=2,
        end_line=3,
    )
    assert nodes["pkg.mod.make_calc"] == FunctionMetadata(
        filepath=os.path.join("pkg", "mod.py"),
        start_line=5,
        end_line=6,
    )
    assert functions_by_file == {
        os.path.join("pkg", "mod.py"): {
            "pkg.mod.Calculator",
            "pkg.mod.Calculator.add",
            "pkg.mod.make_calc",
        }
    }


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

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

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

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    for filepath in graph.dependents:
        assert filepath.endswith(".py")
        assert not any(
            part in filepath
            for part in (".venv", "build", "__pycache__", ".git")
        )
    assert not any("os" in filepath for filepath in graph.dependents)


def test_get_dependency_graph_leaf_module_has_no_entry(git_repo):
    _build_sample_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    assert "mypkg/main.py" not in graph.dependents
    assert "tests/test_app.py" not in graph.dependents


def test_get_dependency_graph_defaults_to_dot_repo(monkeypatch, git_repo):
    _build_sample_project(git_repo)
    monkeypatch.setattr(
        "src.pytest_regsmart.selection.deps_graph.resolve_repo", lambda repo_path=".": git_repo
    )

    graph = get_dependency_graph(graph_level=DIFF_LEVEL.FILE)

    assert graph.dependents["mypkg/service.py"] == {
        "mypkg/main.py",
        "tests/test_app.py",
    }


# ---------------------------------------------------------------------------
# get_dependency_graph (src-layout end-to-end)
# ---------------------------------------------------------------------------


def _build_src_layout_project(repo):
    root = Path(repo.working_tree_dir)
    _write(root, "src/mypkg/__init__.py", "from mypkg.service import run\n")
    _write(
        root,
        "src/mypkg/service.py",
        "def run():\n    return 42\n",
    )
    _write(root, "tests/test_app.py", "from mypkg.service import run\n")
    _write(root, "tests/test_other.py", "from mypkg import service\n")


def test_get_dependency_graph_src_layout(git_repo):
    _build_src_layout_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    assert "tests/test_app.py" in graph.dependents["src/mypkg/service.py"]
    assert "tests/test_other.py" in graph.dependents["src/mypkg/__init__.py"]


def test_get_dependency_graph_src_layout_import_submodule(git_repo):
    root = Path(git_repo.working_tree_dir)
    _write(root, "src/pkg/__init__.py")
    _write(root, "src/pkg/core.py", "def compute():\n    return 1\n")
    _write(root, "tests/test_core.py", "from pkg.core import compute\n")

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    assert "tests/test_core.py" in graph.dependents["src/pkg/core.py"]


# ---------------------------------------------------------------------------
# get_dependency_graph (function-level)
# ---------------------------------------------------------------------------


def _build_function_sample_project(repo):
    root = Path(repo.working_tree_dir)
    _write(root, "mypkg/__init__.py")
    _write(
        root,
        "mypkg/service.py",
        "import os\n"
        "\n"
        "def run():\n"
        "    return os.getcwd()\n"
        "\n"
        "def helper():\n"
        "    return 42\n",
    )
    _write(
        root,
        "mypkg/main.py",
        "from .service import run\n"
        "\n"
        "def main():\n"
        "    return run()\n",
    )
    _write(
        root,
        "tests/test_app.py",
        "from mypkg.service import run, helper\n"
        "\n"
        "def test_app():\n"
        "    assert run()\n"
        "\n"
        "def test_helper():\n"
        "    assert helper()\n",
    )


def test_get_function_dependency_graph_end_to_end(git_repo):
    _build_function_sample_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FUNCTION)

    assert graph.dependents == {
        "mypkg.service.run": {"mypkg.main.main", "tests.test_app.test_app"},
        "mypkg.service.helper": {"tests.test_app.test_helper"},
    }


def test_get_function_dependency_graph_keys_are_unit_ids(git_repo):
    _build_function_sample_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FUNCTION)

    assert "mypkg/service.py" not in graph.dependents
    assert all("/" not in key and not key.endswith(".py") for key in graph.dependents)
    assert set(graph.dependents) <= set(graph.function_nodes)


def test_get_function_dependency_graph_locations(git_repo):
    _build_function_sample_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FUNCTION)

    assert graph.function_nodes["mypkg.service.run"] == FunctionMetadata(
        filepath="mypkg/service.py", start_line=3, end_line=4
    )
    assert graph.function_nodes["mypkg.service.helper"] == FunctionMetadata(
        filepath="mypkg/service.py", start_line=6, end_line=7
    )
    assert graph.function_nodes["tests.test_app.test_helper"] == FunctionMetadata(
        filepath="tests/test_app.py", start_line=6, end_line=7
    )


def test_get_dependency_graph_defaults_to_function_level(git_repo):
    _build_function_sample_project(git_repo)

    graph = get_dependency_graph(git_repo.working_tree_dir)

    assert "mypkg.service.run" in graph.dependents
    assert graph.function_nodes
    assert "mypkg/service.py" not in graph.dependents


# ---------------------------------------------------------------------------
# _readable_python_files
# ---------------------------------------------------------------------------


def test_readable_python_files_keeps_utf8_files_in_order(tmp_path):
    first = _write(tmp_path, "app/first.py", "x = 1\n")
    second = _write(tmp_path, "app/second.py", "y = 2\n")

    assert _readable_python_files([str(first), str(second)]) == [
        str(first),
        str(second),
    ]


def test_readable_python_files_drops_non_utf8_file(tmp_path, caplog):
    good = _write(tmp_path, "app/good.py", "x = 1\n")
    latin1 = _write_bytes(tmp_path, "app/legacy.py", _LATIN1_BYTES)

    with caplog.at_level(logging.WARNING, logger=deps_graph._logger.name):
        readable = _readable_python_files([str(good), str(latin1)])

    assert readable == [str(good)]
    message = caplog.text
    assert "legacy.py" in message
    assert "UnicodeDecodeError" in message


def test_readable_python_files_drops_unopenable_files(tmp_path, caplog):
    good = _write(tmp_path, "app/good.py", "x = 1\n")
    missing = tmp_path / "app" / "missing.py"
    a_directory = tmp_path / "app"

    with caplog.at_level(logging.WARNING, logger=deps_graph._logger.name):
        readable = _readable_python_files([str(good), str(missing), str(a_directory)])

    assert readable == [str(good)]
    assert "FileNotFoundError" in caplog.text
    assert "IsADirectoryError" in caplog.text


# ---------------------------------------------------------------------------
# get_dependency_graph (unreadable files)
# ---------------------------------------------------------------------------


def test_get_dependency_graph_file_level_ignores_non_utf8_files(git_repo, caplog):
    _build_sample_project(git_repo)
    _write_bytes(Path(git_repo.working_tree_dir), "legacy_encoded.py", _LATIN1_BYTES)

    with caplog.at_level(logging.WARNING, logger=deps_graph._logger.name):
        graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    assert graph.dependents["mypkg/service.py"] == {
        "mypkg/main.py",
        "tests/test_app.py",
    }
    assert "legacy_encoded.py" not in graph.dependents
    assert "UnicodeDecodeError" in caplog.text


def test_get_dependency_graph_function_level_ignores_non_utf8_files(git_repo):
    _build_function_sample_project(git_repo)
    _write_bytes(Path(git_repo.working_tree_dir), "legacy_encoded.py", _LATIN1_BYTES)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FUNCTION)

    assert graph.dependents == {
        "mypkg.service.run": {"mypkg.main.main", "tests.test_app.test_app"},
        "mypkg.service.helper": {"tests.test_app.test_helper"},
    }
    assert all("legacy_encoded" not in filepath for filepath in graph.functions_by_file)


# ---------------------------------------------------------------------------
# get_dependency_graph (unparseable files)
# ---------------------------------------------------------------------------


def test_get_dependency_graph_file_level_ignores_unparseable_files(git_repo, caplog):
    _build_sample_project(git_repo)
    _write(Path(git_repo.working_tree_dir), "legacy_py2.py", _PY2_SOURCE)

    with caplog.at_level(logging.WARNING, logger=deps_graph._logger.name):
        graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    assert graph.dependents["mypkg/service.py"] == {
        "mypkg/main.py",
        "tests/test_app.py",
    }
    assert "legacy_py2.py" not in graph.dependents
    assert "SyntaxError" in caplog.text


def test_get_dependency_graph_ignores_repeatedly_unparseable_files(git_repo):
    _build_sample_project(git_repo)
    _unparseable_files(git_repo, 3)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    assert graph.dependents["mypkg/service.py"] == {
        "mypkg/main.py",
        "tests/test_app.py",
    }
    assert not any("legacy_" in filepath for filepath in graph.dependents)


def test_get_dependency_graph_retries_without_the_offending_file(git_repo, monkeypatch):
    root = Path(git_repo.working_tree_dir)
    bad = _write(root, "bad.py", _PY2_SOURCE)
    good = _write(root, "good.py", "x = 1\n")
    received_file_lists = []

    def _fake_build(python_files, working_dir):
        received_file_lists.append(set(python_files))
        if str(bad) in python_files:
            raise SyntaxError("invalid syntax", (str(bad), 1, 1, str(bad)))
        return DependencyGraph(dependents={"good.py": set()})

    monkeypatch.setattr(deps_graph, "_build_file_dependency_graph", _fake_build)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    assert graph.dependents == {"good.py": set()}
    assert received_file_lists == [{str(bad), str(good)}, {str(good)}]


def test_get_dependency_graph_succeeds_when_skips_reach_the_limit(git_repo, monkeypatch):
    _build_sample_project(git_repo)
    _unparseable_files(git_repo, 2)
    monkeypatch.setattr(deps_graph, "_MAX_SKIPPED_FILES", 2)

    graph = get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)

    assert graph.dependents["mypkg/service.py"] == {
        "mypkg/main.py",
        "tests/test_app.py",
    }


def test_get_dependency_graph_raises_when_skips_exceed_the_limit(git_repo, monkeypatch):
    _build_sample_project(git_repo)
    _unparseable_files(git_repo, 3)
    monkeypatch.setattr(deps_graph, "_MAX_SKIPPED_FILES", 2)

    with raises(RuntimeError, match="não puderam ser analisados"):
        get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)


@mark.parametrize(
    "make_exc",
    [
        param(lambda: SyntaxError("no filename"), id="without-filename"),
        param(
            lambda: SyntaxError("invalid syntax", ("<unknown>", 1, 1, "<unknown>")),
            id="filename-outside-the-file-list",
        ),
    ],
)
def test_get_dependency_graph_reraises_unattributable_syntax_error(
    git_repo, monkeypatch, make_exc
):
    _build_sample_project(git_repo)
    monkeypatch.setattr(
        deps_graph, "_build_file_dependency_graph", _raiser(make_exc())
    )

    with raises(SyntaxError):
        get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)


def test_get_dependency_graph_propagates_other_errors(git_repo, monkeypatch):
    _build_sample_project(git_repo)
    monkeypatch.setattr(
        deps_graph, "_build_file_dependency_graph", _raiser(ValueError("boom"))
    )

    with raises(ValueError, match="boom"):
        get_dependency_graph(git_repo.working_tree_dir, graph_level=DIFF_LEVEL.FILE)
