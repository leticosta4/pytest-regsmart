import re
from enum import Enum

from .selection.models import DIFF_LEVEL, DIFF_SOURCE

# ------ Constants ------

DATA_DIR = "pytest_ranked_selection_data"

# Default amount of historical test run results to store per test.
DEFAULT_HIST_LEN = 50

DEFAULT_WEIGHT = "0-1"

DEFAULT_SEED = 0

DEFAULT_REPLAY = None


class RANK_LEVEL(str, Enum):
    """The test group level at which the test suites are reordered.
    Tests within each group follows the pytest default order.
    https://docs.pytest.org/en/stable/reference/fixtures.html#fixtures
    """
    PUT = "put"
    FUNCTION = "function"
    MODULE = "module"

    def __str__(self) -> str:
        return self.value

DEFAULT_RANK_LEVEL = RANK_LEVEL.PUT

DEFAULT_DIFF_LEVEL = DIFF_LEVEL.FUNCTION

DEFAULT_DIFF_SOURCE = DIFF_SOURCE.COMMIT

DIFF_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

DEFAULT_BRANCH_CANDIDATES = ("main", "master")
COMMIT_BRANCH_CANDIDATES = ("origin/main", "origin/master", "main", "master")

BASE_BRANCH_CANDIDATES: dict[DIFF_SOURCE, tuple[str, ...]] = {
    DIFF_SOURCE.COMMIT: COMMIT_BRANCH_CANDIDATES,
    DIFF_SOURCE.WORKTREE: DEFAULT_BRANCH_CANDIDATES,
}
