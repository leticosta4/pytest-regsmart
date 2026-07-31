from enum import Enum
from git import Repo

# ------ Constants ------

DATA_DIR = "pytest_ranked_selection_data"

# Default amount of historical test run results to store per test.
DEFAULT_HIST_LEN = 50

DEFAULT_WEIGHT = "1-0"

DEFAULT_SEED = 0

DEFAULT_REPLAY = None


class LEVEL(str, Enum):
    """The test group level at which the test suites are reordered.
    Tests within each group follows the pytest default order.
    https://docs.pytest.org/en/stable/reference/fixtures.html#fixtures
    """
    PUT = "put"
    FUNCTION = "function"
    MODULE = "module"

DEFAULT_LEVEL = LEVEL.PUT

#diretorio base: repo raiz do repositorio git para pegar o diff e para calcular o grafo de deps
REPOSITORY_DIR = Repo(".")  #talvez vou deixar isso configuravel via flag depois, mas por enquanto vou deixar fixo no repo raiz
