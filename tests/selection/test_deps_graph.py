from __future__ import annotations

import logging
import os
from pathlib import Path

from pyan.analyzer import CallGraphVisitor
from pytest import mark, param, raises

from pytest_regsmart.const import DIFF_LEVEL
from src.pytest_regsmart.selection import deps_graph
from src.pytest_regsmart.selection.deps_graph import (
    _build_function_dependency_graph,
    _build_import_name_to_path,
    _convert_module_to_relative_path,
    _extract_function_nodes,
    _find_py_files,
    _invert_dependency_map,
    _readable_python_files,
    get_dependency_graph,
)
from src.pytest_regsmart.selection.models import (
    DependencyGraph,
    FunctionMetadata,
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
    _write(tmp_path, ".pixi/envs/py312/lib/python3.12/poplib.py")

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


def test_function_graph_records_tests_that_run_nested_pytest(tmp_path):
    _write(tmp_path, "pkg/service.py", "def changed():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_nested.py",
        "class TestDistribution:\n"
        "    def test_child_pytest(self, pytester):\n"
        "        pytester.runpytest_subprocess('--help')\n"
        "\n"
        "    def test_regular(self):\n"
        "        assert True\n",
    )

    python_files = [str(path) for path in tmp_path.rglob("*.py")]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    assert graph.subprocess_tests == {"tests.test_nested.TestDistribution.test_child_pytest"}


def test_function_graph_keeps_pyan_edges_if_dynamic_pass_fails(
    tmp_path, monkeypatch, caplog
):
    _write(tmp_path, "pkg/service.py", "def run():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_service.py",
        "from pkg.service import run\n"
        "def test_run():\n"
        "    run()\n",
    )

    def fail_dynamic_pass(*args, **kwargs):
        raise RuntimeError("AST pass failed")

    monkeypatch.setattr(
        deps_graph, "get_dynamic_method_dependencies", fail_dynamic_pass
    )
    python_files = [str(path) for path in tmp_path.rglob("*.py")]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    assert graph.dependents["pkg.service.run"] == {"tests.test_service.test_run"}
    assert "ignoring inheritance-based dependencies (RuntimeError)" in caplog.text


def test_function_graph_resolves_qualified_calls_during_pyan_visit(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "def __getattr__(name):\n    raise AttributeError(name)\n")
    _write(tmp_path, "pkg/__init__.pyi", "from .feature.core import griffinlim as griffinlim\n")
    _write(
        tmp_path,
        "pkg/feature/__init__.py",
        "def __getattr__(name):\n    raise AttributeError(name)\n",
    )
    _write(
        tmp_path,
        "pkg/feature/inverse.py",
        "from .core import griffinlim\n\n"
        "def mel_to_audio():\n    return griffinlim()\n",
    )
    _write(tmp_path, "pkg/feature/core.py", "def griffinlim():\n    return None\n")
    _write(tmp_path, "pkg/other.py", "def griffinlim():\n    return None\n")
    _write(
        tmp_path,
        "tests/test_pkg.py",
        "import pkg as audio\n\n"
        "def test_qualified_call():\n    audio.feature.inverse.mel_to_audio()\n\n"
        "def test_reexported_call():\n    audio.griffinlim()\n\n"
        "def test_shadowed_module(audio):\n    audio.feature.inverse.mel_to_audio()\n",
    )

    python_files = [
        str(path)
        for path in (*tmp_path.rglob("*.py"), *tmp_path.rglob("*.pyi"))
    ]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    assert "tests.test_pkg.test_qualified_call" in graph.dependents[
        "pkg.feature.inverse.mel_to_audio"
    ]
    assert "tests.test_pkg.test_shadowed_module" not in graph.dependents[
        "pkg.feature.inverse.mel_to_audio"
    ]
    assert graph.dependents["pkg.feature.core.griffinlim"] == {
        "pkg.feature.inverse.mel_to_audio",
        "tests.test_pkg.test_reexported_call",
    }
    assert "tests.test_pkg.test_reexported_call" not in graph.dependents.get(
        "pkg.other.griffinlim", set()
    )


def test_function_graph_follows_reexported_submodules_and_star_imports(tmp_path):
    _write(
        tmp_path,
        "networkx/__init__.py",
        "from . import bipartite\nfrom .bipartite import *\n",
    )
    _write(
        tmp_path,
        "networkx/bipartite/__init__.py",
        "from .basic import *\nfrom .algorithms import clustering\n",
    )
    _write(
        tmp_path,
        "networkx/bipartite/basic.py",
        "__all__ = ['is_bipartite']\n"
        "def is_bipartite(graph):\n    return True\n",
    )
    _write(
        tmp_path,
        "networkx/bipartite/algorithms.py",
        "from .basic import is_bipartite\n"
        "def clustering(graph):\n    return is_bipartite(graph)\n",
    )
    _write(
        tmp_path,
        "tests/test_bipartite.py",
        "import networkx as nx\n"
        "def test_root_reexport():\n    nx.is_bipartite(None)\n"
        "def test_submodule_reexport():\n    nx.bipartite.is_bipartite(None)\n"
        "def test_intermediate_algorithm():\n    nx.bipartite.clustering(None)\n",
    )

    python_files = [str(path) for path in tmp_path.rglob("*.py")]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    assert graph.dependents["networkx.bipartite.basic.is_bipartite"] == {
        "tests.test_bipartite.test_root_reexport",
        "tests.test_bipartite.test_submodule_reexport",
        "networkx.bipartite.algorithms.clustering",
    }
    assert "tests.test_bipartite.test_intermediate_algorithm" in graph.dependents[
        "networkx.bipartite.algorithms.clustering"
    ]


def test_function_graph_follows_reexported_function_alias(tmp_path):
    _write(
        tmp_path,
        "networkx/__init__.py",
        "from . import bipartite\n",
    )
    _write(
        tmp_path,
        "networkx/bipartite/__init__.py",
        "from .cluster import *\n",
    )
    _write(
        tmp_path,
        "networkx/bipartite/cluster.py",
        "__all__ = ['clustering', 'latapy_clustering']\n"
        "def latapy_clustering(graph):\n    return 0\n"
        "clustering = latapy_clustering\n",
    )
    _write(
        tmp_path,
        "tests/test_cluster.py",
        "import networkx as nx\n"
        "def test_alias_through_reexport():\n    nx.bipartite.clustering(None)\n",
    )

    python_files = [str(path) for path in tmp_path.rglob("*.py")]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    assert "tests.test_cluster.test_alias_through_reexport" in graph.dependents[
        "networkx.bipartite.cluster.latapy_clustering"
    ]


def test_function_graph_tracks_inherited_dispatch_and_local_instances(tmp_path):
    _write(
        tmp_path,
        "pkg/api.py",
        "class Base:\n"
        "    def run(self):\n"
        "        return self.compute()\n"
        "    def compute(self):\n"
        "        return 0\n"
        "class Child(Base):\n"
        "    def compute(self):\n"
        "        return 1\n"
        "class Unrelated:\n"
        "    def compute(self):\n"
        "        return 2\n",
    )
    _write(
        tmp_path,
        "tests/test_api.py",
        "from pkg.api import Child\n"
        "def test_inherited_api():\n"
        "    instance = Child()\n"
        "    assert instance.run() == 1\n",
    )

    python_files = [str(path) for path in tmp_path.rglob("*.py")]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    assert "pkg.api.Base.run" in graph.dependents["pkg.api.Child.compute"]
    assert "tests.test_api.test_inherited_api" in graph.dependents[
        "pkg.api.Base.run"
    ]
    assert "tests.test_api.test_inherited_api" not in graph.dependents.get(
        "pkg.api.Unrelated.compute", set()
    )


def test_function_graph_resolves_inline_instance_of_inherited_api(tmp_path):
    _write(
        tmp_path,
        "pkg/api.py",
        "class Base:\n"
        "    def run(self):\n"
        "        return self.compute()\n"
        "class Child(Base):\n"
        "    def compute(self):\n"
        "        return 1\n",
    )
    _write(
        tmp_path,
        "tests/test_api.py",
        "from pkg.api import Child\n"
        "def test_inline_instance():\n"
        "    assert Child().run() == 1\n",
    )

    python_files = [str(path) for path in tmp_path.rglob("*.py")]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    assert "tests.test_api.test_inline_instance" in graph.dependents[
        "pkg.api.Base.run"
    ]


def test_function_graph_tracks_inherited_public_api_without_override(tmp_path):
    _write(
        tmp_path,
        "pkg/api.py",
        "class Base:\n"
        "    def fit(self, value):\n"
        "        return self._validate(value)\n"
        "    def _validate(self, value):\n"
        "        return value\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        return cls()\n"
        "class Child(Base):\n"
        "    pass\n"
        "class Unrelated:\n"
        "    def fit(self, value):\n"
        "        return value\n",
    )
    _write(tmp_path, "pkg/__init__.py", "from .api import Child\n")
    _write(
        tmp_path,
        "tests/test_api.py",
        "from pkg import Child\n"
        "def test_constructed_subclass():\n"
        "    instance = Child()\n"
        "    instance.fit(1)\n"
        "def test_classmethod_constructed_subclass():\n"
        "    Child.create().fit(1)\n",
    )

    python_files = [str(path) for path in tmp_path.rglob("*.py")]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    def affected_by(node: str) -> set[str]:
        affected = set()
        pending = [node]
        while pending:
            current = pending.pop()
            for dependent in graph.dependents.get(current, set()):
                if dependent not in affected:
                    affected.add(dependent)
                    pending.append(dependent)
        return {item for item in affected if item.startswith("tests.")}

    assert affected_by("pkg.api.Base.fit") == {
        "tests.test_api.test_constructed_subclass",
        "tests.test_api.test_classmethod_constructed_subclass",
    }
    assert "pkg.api.Unrelated" not in graph.dependents.get("pkg.api.Base", set())


def test_function_graph_resolves_local_import_of_concrete_class(tmp_path):
    _write(
        tmp_path,
        "pkg/api.py",
        "class Base:\n"
        "    def run(self):\n"
        "        return 1\n"
        "class Child(Base):\n"
        "    pass\n",
    )
    _write(tmp_path, "pkg/__init__.py", "from .api import Child\n")
    _write(
        tmp_path,
        "tests/test_api.py",
        "def test_local_import():\n"
        "    from pkg import Child\n"
        "    Child().run()\n",
    )

    python_files = [str(path) for path in tmp_path.rglob("*.py")]
    graph = _build_function_dependency_graph(python_files, str(tmp_path))

    assert "tests.test_api.test_local_import" in graph.dependents[
        "pkg.api.Base.run"
    ]


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


def _lazy_package(tmp_path: Path) -> None:
    """Package whose attributes are created lazily (``__getattr__`` + stub)."""
    _write(tmp_path, "pkg/__init__.py", "def __getattr__(name):\n    raise AttributeError(name)\n")
    _write(
        tmp_path,
        "pkg/__init__.pyi",
        "from .dag import descendants as descendants\n"
        "from .dag import ancestors as ancestors\n",
    )
    _write(
        tmp_path,
        "pkg/dag.py",
        "def descendants(graph):\n    return set()\n\n"
        "def ancestors(graph):\n    return set()\n",
    )


def _function_graph_for(tmp_path: Path):
    python_files = [
        str(path) for path in (*tmp_path.rglob("*.py"), *tmp_path.rglob("*.pyi"))
    ]
    return _build_function_dependency_graph(python_files, str(tmp_path))


def test_function_graph_links_functions_referenced_without_a_call(tmp_path):
    _lazy_package(tmp_path)
    _write(
        tmp_path,
        "tests/test_refs.py",
        "import pytest\n"
        "import pkg as nx\n\n"
        "def test_alias():\n"
        "    descendants = nx.descendants\n"
        "    descendants(None)\n\n"
        "def test_argument():\n"
        "    pytest.raises(ValueError, nx.descendants, None)\n\n"
        "def test_list_element():\n"
        "    for func in [nx.descendants]:\n"
        "        func(None)\n\n"
        "def test_shadowed(nx):\n"
        "    nx.descendants(None)\n\n"
        "def test_unrelated():\n"
        "    nx.ancestors(None)\n",
    )

    graph = _function_graph_for(tmp_path)

    assert graph.dependents["pkg.dag.descendants"] == {
        "tests.test_refs.test_alias",
        "tests.test_refs.test_argument",
        "tests.test_refs.test_list_element",
    }
    assert graph.dependents["pkg.dag.ancestors"] == {"tests.test_refs.test_unrelated"}


def test_function_graph_links_parametrized_tests_through_module_variables(tmp_path):
    _lazy_package(tmp_path)
    _write(
        tmp_path,
        "tests/test_params.py",
        "import pytest\n"
        "import pkg as nx\n\n"
        "def descendants_helper(graph):\n"
        "    return nx.descendants(graph)\n\n"
        "is_funcs = {'descendants': (descendants_helper,)}\n"
        "all_funcs = is_funcs | {}\n"
        "params = [pytest.param(fn[0], id=key) for key, fn in all_funcs.items()]\n\n"
        "@pytest.mark.parametrize('func', params)\n"
        "def test_through_variables(func):\n"
        "    func(None)\n\n"
        "@pytest.mark.parametrize('func', [nx.descendants])\n"
        "def test_qualified_in_decorator(func):\n"
        "    func(None)\n\n"
        "class TestCases:\n"
        "    CASES = [nx.descendants]\n\n"
        "    @pytest.mark.parametrize('func', CASES)\n"
        "    def test_class_variable(self, func):\n"
        "        func(None)\n\n"
        "def test_body_reads_variable():\n"
        "    for funcs in all_funcs.values():\n"
        "        funcs[0](None)\n\n"
        "@pytest.mark.parametrize('func', [nx.ancestors])\n"
        "def test_unrelated(func):\n"
        "    func(None)\n",
    )

    graph = _function_graph_for(tmp_path)

    assert graph.dependents["tests.test_params.descendants_helper"] >= {
        "tests.test_params.test_through_variables",
        "tests.test_params.test_body_reads_variable",
    }
    assert {
        "tests.test_params.test_qualified_in_decorator",
        "tests.test_params.TestCases.test_class_variable",
    } <= graph.dependents["pkg.dag.descendants"]
    affected = graph.dependents["pkg.dag.descendants"] | graph.dependents[
        "tests.test_params.descendants_helper"
    ]
    assert "tests.test_params.test_unrelated" not in affected
    assert graph.dependents["pkg.dag.ancestors"] == {"tests.test_params.test_unrelated"}


def test_function_graph_expands_module_variables_imported_from_helpers(tmp_path):
    _lazy_package(tmp_path)
    _write(tmp_path, "tests/__init__.py")
    _write(
        tmp_path,
        "tests/common.py",
        "import pkg as nx\n\nSHARED = [nx.descendants]\nOTHER = [nx.ancestors]\n",
    )
    _write(
        tmp_path,
        "tests/test_shared.py",
        "import pytest\n"
        "from .common import SHARED, OTHER\n\n"
        "@pytest.mark.parametrize('func', SHARED)\n"
        "def test_shared(func):\n"
        "    func(None)\n\n"
        "@pytest.mark.parametrize('func', OTHER)\n"
        "def test_other(func):\n"
        "    func(None)\n",
    )

    graph = _function_graph_for(tmp_path)

    assert graph.dependents["pkg.dag.descendants"] == {"tests.test_shared.test_shared"}
    assert graph.dependents["pkg.dag.ancestors"] == {"tests.test_shared.test_other"}


def test_function_graph_handles_cyclic_module_variables(tmp_path):
    _write(
        tmp_path,
        "tests/test_cycle.py",
        "def helper():\n    return 1\n\n"
        "A = [helper]\n"
        "B = A\n"
        "A = B\n\n"
        "def test_cycle():\n"
        "    for func in A:\n"
        "        func()\n",
    )

    graph = _function_graph_for(tmp_path)

    assert graph.dependents["tests.test_cycle.helper"] == {"tests.test_cycle.test_cycle"}


def test_indexed_get_node_matches_pyan_lookup(tmp_path):
    from pyan.analyzer import CallGraphVisitor as PyanVisitor

    from src.pytest_regsmart.selection.models import _ModuleQualifiedCallGraphVisitor

    files = [
        _write(tmp_path, "pkg/__init__.py", "from .core import run\n"),
        _write(
            tmp_path,
            "pkg/core.py",
            "class Base:\n    def run(self):\n        return 1\n"
            "class Child(Base):\n    def run(self):\n        return super().run()\n"
            "def run():\n    return Child().run()\n",
        ),
        _write(tmp_path, "tests/test_core.py", "from pkg.core import run\n\n\ndef test_run():\n    assert run()\n"),
    ]
    kwargs = {
        "filenames": [str(f) for f in files],
        "root": str(tmp_path),
        "logger": logging.getLogger(__name__),
    }
    indexed = _ModuleQualifiedCallGraphVisitor(**kwargs)
    reference = PyanVisitor(**kwargs)

    def edges(visitor):
        return {
            (src.get_name(), dst.get_name())
            for src, targets in visitor.uses_edges.items()
            for dst in targets
        }

    # Same graph as pyan's own linear lookup.
    assert edges(indexed) == edges(reference)
    # Every lookup returns pyan's first match, also after a list is replaced.
    for name, nodes in list(indexed.nodes.items()):
        for node in nodes:
            first = next(n for n in nodes if n.namespace == node.namespace)
            assert indexed.get_node(node.namespace, name) is first
        indexed.nodes[name] = list(reversed(nodes))
        for node in nodes:
            first = next(n for n in indexed.nodes[name] if n.namespace == node.namespace)
            assert indexed.get_node(node.namespace, name) is first


def test_module_trees_are_the_asts_pyan_parsed(tmp_path):
    import ast

    from src.pytest_regsmart.selection.deps_graph import _module_trees
    from src.pytest_regsmart.selection.models import (
        _ModuleQualifiedCallGraphVisitor,
        _QuietScopes,
    )

    files = [
        _write(tmp_path, "pkg/__init__.py", "from .core import run\n"),
        _write(
            tmp_path,
            "pkg/core.py",
            "import os\n\n\nclass Base:\n    def run(self):\n        return [lambda x: x for _ in range(2)]\n\n\n"
            "def run(value: int = 1):\n    return Base().run(), os.sep, {k: v for k, v in {}.items()}\n",
        ),
        _write(tmp_path, "tests/test_core.py", "from pkg.core import run\n\n\ndef test_run():\n    assert run()\n"),
    ]
    graph = _ModuleQualifiedCallGraphVisitor(
        filenames=[str(f) for f in files], root=str(tmp_path), logger=logging.getLogger(__name__)
    )

    trees = _module_trees(graph)

    # pyan keeps an unmodified ast.Module per analyzed file, so the plugin's
    # own AST passes can reuse it instead of parsing the file again.
    assert set(trees) == {os.path.normpath(os.path.abspath(f)) for f in files}
    for path in files:
        fresh = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert ast.dump(trees[os.path.normpath(os.path.abspath(path))]) == ast.dump(fresh)

    # The scopes mapping keeps dict behaviour, with a constant-size repr.
    assert isinstance(graph.scopes, _QuietScopes)
    assert "pkg.core" in graph.scopes
    assert repr(graph.scopes) == f"<{len(graph.scopes)} scopes>"


@mark.parametrize(
    "source",
    ["a", "a.b", "pkg.mod.Klass", "f()", "f().x", "a[0]", "a.b[0].c", "'Klass'", "x.y()", "(a or b).c", "obj.attr.method"],
)
def test_dotted_name_matches_unparse_for_name_chains(source):
    import ast

    from src.pytest_regsmart.selection.dynamic_dispatch import _dotted_name

    expression = ast.parse(source, mode="eval").body
    node = expression
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Name):
        assert _dotted_name(expression) == ast.unparse(expression)
    else:
        assert _dotted_name(expression) is None


def _doctested_module(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from pkg import tr\n")
    _write(
        tmp_path,
        "pkg/tr.py",
        "def rot(x):\n    '''\n    >>> rot(1)\n    1\n    '''\n    return x\n\n"
        "class Box:\n    def area(self):\n        return 0\n",
    )


def test_function_graph_links_module_passed_as_argument(tmp_path):
    _doctested_module(tmp_path)
    _write(
        tmp_path,
        "tests/test_doc.py",
        "import doctest\nimport pkg.tr\n\n"
        "def test_doctest():\n    doctest.testmod(pkg.tr)\n\n"
        "def test_local_import():\n    import pkg\n    doctest.testmod(m=pkg.tr)\n",
    )

    graph = _function_graph_for(tmp_path)

    for member in ("pkg.tr.rot", "pkg.tr.Box", "pkg.tr.Box.area"):
        assert {"tests.test_doc.test_doctest", "tests.test_doc.test_local_import"} <= (
            graph.dependents.get(member, set())
        ), member


def test_function_graph_links_module_argument_through_helper_module(tmp_path):
    _doctested_module(tmp_path)
    _write(tmp_path, "tests/generic.py", "import pkg\n")
    _write(
        tmp_path,
        "tests/test_doc.py",
        "try:\n    from . import generic as g\nexcept BaseException:\n    import generic as g\n"
        "import doctest\n\n"
        "def test_doctest():\n    doctest.testmod(g.pkg.tr)\n",
    )

    graph = _function_graph_for(tmp_path)

    assert "tests.test_doc.test_doctest" in graph.dependents.get("pkg.tr.rot", set())


def test_function_graph_module_argument_ignores_non_modules_and_shadowing(tmp_path):
    _doctested_module(tmp_path)
    _write(tmp_path, "pkg/other.py", "def k():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_doc.py",
        "import pkg.tr\nimport pkg.other\n\n"
        "def test_function_argument():\n    list(map(pkg.tr.rot, [1]))\n\n"
        "def test_shadowed(pkg):\n    print(pkg.other)\n",
    )

    graph = _function_graph_for(tmp_path)

    # A function passed as an argument links only to that function.
    assert "tests.test_doc.test_function_argument" in graph.dependents["pkg.tr.rot"]
    assert "tests.test_doc.test_function_argument" not in graph.dependents.get(
        "pkg.tr.Box.area", set()
    )
    # A parameter named like the package is not the module.
    assert "tests.test_doc.test_shadowed" not in graph.dependents.get("pkg.other.k", set())


def test_function_graph_follows_calls_through_dotted_import(tmp_path):
    _doctested_module(tmp_path)
    _write(
        tmp_path,
        "tests/test_dotted.py",
        "import pkg.tr\n\ndef test_call():\n    assert pkg.tr.rot(1) == 1\n",
    )

    graph = _function_graph_for(tmp_path)

    assert "tests.test_dotted.test_call" in graph.dependents.get("pkg.tr.rot", set())
