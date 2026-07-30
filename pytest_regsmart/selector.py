from git import Repo


def get_git_diff(): #vai considerar sempre a branch atual e a branch base (main/master) - pelo menos por enquanto
    # vou ter que ver se tem unstaged tb
    # tenho que pegar da branch atual e fazer o git diff com a branch base - main/master
    # como vou conseguir a branch base? talvez seja melhor pegar o commit mais recente da branch base e fazer o diff com ele
    repo = Repo(".")
    current_branch = repo.active_branch.name
    base_branch = "main"  # ou "master", dependendo do seu repositório

    complete_diff = repo.git.diff(f"{base_branch}..{current_branch}", name_only=True)


    #olhar melhor depois:
    # Initialize commit references
    #hcommit = repo.head.commit

    # 1. Compare Working Directory vs Staging Area (Index)
    #diffs = repo.index.diff(None)

    # 2. Compare Staging Area (Index) vs HEAD
    #diffs = repo.index.diff("HEAD")

    # 3. Compare HEAD Commit vs Working Directory
    #diffs = hcommit.diff(None)

    pass


def get_dependency_graph():
    pass


def get_affected_tests():
    pass


def run_rts():
    pass

#rodar o git diff pra ver a diferença
#guardar os trechos
#talvez em paralelo: rodar o pyan3 pra pegar o grafo de dependencias
#funcao pra correlacionar os trechos com o grafo de dependencias e achar testes afetados
#pega a nova lista de testes e manda para o ranker