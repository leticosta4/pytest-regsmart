from collections import defaultdict
import logging
import os
from dataclasses import dataclass
from pyan.modvis import ImportVisitor

from .const import REPOSITORY_DIR
#inicialmente tenho que tentar gerar a forma mais simples só com os arquivos, nao precisa das funções 
#vou usar a API do pyan3, não o CLI

@dataclass
class DependencyGraph:
    dependents: dict[str, set[str]]  # chave: módulo, valor: conjunto de módulos que dependem/sao afetados por ele


def _find_py_files(working_dir: str) -> list[str]:
    excludes = [".venv", ".git", "__pycache__", "dist", "build"]

    py_files = []
    for dirpath, dirnames, filenames in os.walk(working_dir):
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.endswith(".egg-info")] #nova lista de diretorios só dos arquivos core para checar
        for filename in filenames:
            if filename.endswith(".py"):
                py_files.append(os.path.join(dirpath, filename)) #monta o caminho completo
    return py_files


def _build_module_relative_path(fullpaths, working_dir: str) -> dict[str, str]:
    """Converte nomes de módulo do pyan3 pra caminhos relativos ao repo (match com o diff).

    Ex: "pytest_regsmart.selector" -> "pytest_regsmart/selector.py"
    """
    return {
        module: os.path.relpath(fullpath, working_dir)
        for module, fullpath in fullpaths.items()
    }

def _invert_dependency_graph(
        module_imports: dict[str, set[str]],
        module_to_path: dict[str, str]
    ) -> DependencyGraph:
    """Conversao de 'modulo importa X' para 'arquivo X é usado por módulo'.

    Ex: se plugin.py importa selector.py, o retorno tem
    selector.py -> {plugin.py} (selector.py afeta plugin.py se mudar)
    """

    dependents = defaultdict(set) #versão de dict que não dá KeyError quando acessa uma chave que ainda não existe; subclasssed e dict: https://www.geeksforgeeks.org/python/defaultdict-in-python/

    for importer, imported_modules in module_imports.items():
        importer_path = module_to_path.get(importer)
        for imported in imported_modules:
            imported_path = module_to_path.get(imported)
            if imported_path is None:
                continue  # nao importa arquivo no repo
            dependents[imported_path].add(importer_path)


    return DependencyGraph(dependents=dict(dependents))

def get_dependency_graph() -> DependencyGraph:
    working_dir = REPOSITORY_DIR.working_tree_dir
    python_files = _find_py_files(working_dir)

    graph = ImportVisitor(filenames=python_files, logger=logging.getLogger(__name__), root=working_dir)
    #graph.modules: módulo -> set de módulos importados por ele
    #graph.fullpaths: módulo -> caminho absoluto do arquivo

    module_to_path = _build_module_relative_path(graph.fullpaths, working_dir)
    dependents_by_file =  _invert_dependency_graph(graph.modules, module_to_path)  #quero inverter pra ficar modulo -> quem IMPORTA esse modulo / quem é afetado por ele 
    
    return dependents_by_file
