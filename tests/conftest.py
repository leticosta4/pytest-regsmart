from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

pytest_plugins = ["pytester"]


@pytest.fixture
def git_repo(tmp_path) -> Repo:
    repo = Repo.init(tmp_path)
    writer = repo.config_writer()
    writer.set_value("user", "name", "Test")
    writer.set_value("user", "email", "test@test.com")
    writer.release()
    return repo


@pytest.fixture
def commit_file(git_repo):
    def _commit_file(filename: str, content: str = "") -> Path:
        filepath = Path(git_repo.working_tree_dir) / filename
        filepath.write_text(content)
        git_repo.index.add(filename)
        git_repo.index.commit(f"Add {filename}")
        return filepath

    return _commit_file


@pytest.fixture
def mytester(pytester):
    pytester.makefile(
        ".ini",
        pytest="""
            [pytest]
            console_output_style = classic
            """,
    )
    repo = Repo.init(pytester.path)
    writer = repo.config_writer()
    writer.set_value("user", "name", "Test")
    writer.set_value("user", "email", "test@test.com")
    writer.release()
    (pytester.path / ".gitignore").write_text("__pycache__/\n")
    repo.index.add([".gitignore"])
    repo.index.commit("chore: baseline")
    yield pytester


@pytest.fixture
def selection_project(pytester):
    """Repo git com módulo de produção + testes que o importam, tudo commitado.

    Permite exercitar a seleção de verdade: o teste altera `service.py`
    (produção) para gerar um diff e selecionar só os testes dependentes.
    Retorna (Path do projeto, Repo).
    """
    pytester.makefile(
        ".ini",
        pytest="""
            [pytest]
            console_output_style = classic
            """,
    )
    repo = Repo.init(pytester.path)
    writer = repo.config_writer()
    writer.set_value("user", "name", "Test")
    writer.set_value("user", "email", "test@test.com")
    writer.release()

    (pytester.path / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    pytester.makepyfile(
        service="""
            def run():
                return 42
            """,
        test_service="""
            import time
            from service import run

            def test_service_fast():
                time.sleep(0.05)
                assert run() == 42

            def test_service_slow():
                time.sleep(0.5)
                assert run() == 42
            """,
        test_other="""
            import time
            from service import run

            def test_other_run():
                time.sleep(0.2)
                assert run() == 42
            """,
        test_unrelated="""
            def test_unrelated():
                assert True
            """,
    )
    repo.index.add(
        [
            ".gitignore",
            "pytest.ini",
            "service.py",
            "test_service.py",
            "test_other.py",
            "test_unrelated.py",
        ]
    )
    repo.index.commit("chore: baseline")
    yield pytester, repo
