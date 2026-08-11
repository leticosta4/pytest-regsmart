from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass

from pyan.modvis import ImportVisitor

from .git_manager import resolve_repo

#initially I'll try the simplest form using only files; functions are not needed yet
#use the pyan3 API, not the CLI

@dataclass
class DependencyGraph:
    dependents: dict[str, set[str]]  #key: module, value: set of modules that depend on / are affected by it


def _find_py_files(working_dir: str) -> list[str]:
    excludes = [".venv", ".git", "__pycache__", "dist", "build", "venv", "site-packages"]

    py_files = []
    for dirpath, dirnames, filenames in os.walk(working_dir):
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.endswith(".egg-info")]  # keep only core directories to check
        for filename in filenames:
            if filename.endswith(".py"):
                py_files.append(os.path.join(dirpath, filename)) #build the full path
    return py_files


def _build_module_relative_path(fullpaths, working_dir: str) -> dict[str, str]:
    """Convert pyan3 module names to paths relative to the repo (to match the diff).

    E.g.: "pytest_regsmart.selector" -> "pytest_regsmart/selector.py"
    """
    return {
        module: os.path.relpath(fullpath, working_dir)
        for module, fullpath in fullpaths.items()
    }


def _invert_dependency_graph(
        module_imports: dict[str, set[str]],
        module_to_path: dict[str, str]
    ) -> DependencyGraph:
    """Invert 'module imports X' into 'file X is used by module'.

    E.g.: if plugin.py imports selector.py, the result contains
    selector.py -> {plugin.py} (changing selector.py affects plugin.py)
    """

    dependents = defaultdict(set) #dict that does not raise KeyError on missing keys; a dict subclass: https://www.geeksforgeeks.org/python/defaultdict-in-python/

    for importer, imported_modules in module_imports.items():
        importer_path = module_to_path.get(importer)
        for imported in imported_modules:
            imported_path = module_to_path.get(imported)
            if imported_path is None:
                continue  #doesnt import a file in the repo
            dependents[imported_path].add(importer_path)


    return DependencyGraph(dependents=dict(dependents))


def get_dependency_graph(repo_path: str = ".") -> DependencyGraph:
    repo = resolve_repo(repo_path)
    working_dir = repo.working_tree_dir
    python_files = _find_py_files(working_dir)

    graph = ImportVisitor(filenames=python_files, logger=logging.getLogger(__name__), root=working_dir)
    #graph.modules: module -> set of modules imported by it
    #graph.fullpaths: module -> absolute file path

    module_to_path = _build_module_relative_path(graph.fullpaths, working_dir)
    dependents_by_file = _invert_dependency_graph(graph.modules, module_to_path)  # invert so it becomes module -> who IMPORTS it / who is affected by it
    
    return dependents_by_file
