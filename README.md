# pytest-regsmart

A Pytest plugin that implements Regression Test Selection (RTS) and Regression Test Prioritization (RTP) for faster regression fault detection.

This [pytest](https://github.com/pytest-dev/pytest) plugin allows you to find regression test failures faster and receive testing feedback sooner from CI build.
When enabled with `--regsmart`, it first **selects** only the test files affected by the changes since the last baseline (RTS), then **prioritizes** them so that the tests that are faster or recently failed run earlier (RTP).

## Installation

```bash
uv pip install pytest-regsmart
```

Or using pip:

```bash
pip install pytest-regsmart
```

## Usage

Pytest will automatically find the plugin and use it when you run ``pytest``.
You can run `pytest-regsmart` with its default configuration, which selects only the affected tests and runs faster tests first, by passing the ``--regsmart`` option:

```bash
pytest --regsmart
```

Note that `--regsmart` requires the project to be a `git` repository (the regression test selection is computed from the changes since the base branch). Running it outside a git repo raises a `UsageError`.

The **base branch must be resolvable in the local clone** for the diff to be computed. `pytest-regsmart` always compares the current branch against the repository's default branch — `main`, or `master` if that is its name — resolved first as a local branch and then as the `origin/main` (or `origin/master`) remote-tracking ref. On a shallow clone (e.g. `actions/checkout` with the default `fetch-depth: 1`), the base branch is not fetched, so it cannot be resolved — `pytest-regsmart` raises a `UsageError` telling you what to fix instead of silently running the whole suite. In CI, fetch the full history (see [Deployment](./DEPLOYMENT.md)).

Before the test run starts, if `--regsmart` is passed, the terminal header will report `pytest-regsmart`'s configuration of this run, for example:

```
Starting Smart Regression Test Management (RTS + RTP)
Using --diff-level=function
Using --rank-weight=1-0
Using --rank-level=put
Using --rank-hist-len=50
Using --rank-seed=123
Using --rank-replay=None
```

After the test run finishes, the terminal summary will show the overhead of `pytest-regsmart` in this run, for example:

```
=================================== pytest-regsmart summary info ====================================
Time to run the regression test selection (s): 0.0003604120544433594
Time to run the regression test prioritization (s): 0.0004608631134033203
Time to collect test features (s): 0.0004608631134033203
```


### Disabling ranking (RTP)

You can disable the regression test prioritization while keeping the plugin active with the `--no-rank` flag:

```bash
pytest --regsmart --no-rank
```

This is useful when you want to run only the selected tests (RTS) without reordering them (RTP).
With `--no-rank`, the header instead reports:

```
Starting RTS (Regression Test Selection)
Using --no-rank (RTP disabled).
```

Note that `--no-rank` **cannot be combined with other `--rank-*` flags**: passing any of them together raises a `UsageError`. It only disables the prioritization step; the regression test selection still applies.

### Choosing the diff granularity

You can set at which level the changes are identified and tests are selected, by passing the optional `--diff-level` flag in one of these values: `function`, `file`. For example:

```bash
pytest --regsmart --diff-level=file
```

- `function` (default): maps each changed line range from the git diff to the functions or methods that contain it, then selects only the test functions affected directly or transitively through the call graph. Diff hunks outside any function (e.g., imports or module constants) fall back to selecting the whole file.
- `file`: a change in one module selects every test file that transitively depends on it, which may include more tests than strictly necessary.

This option can also be configured via the `diff_level` ini option (see [Setting configurable options via config file](#setting-configurable-options-via-config-file)).

### Optimizing test prioritization heuristics

You can set the weights of different test prioritization heuristics by passing the optional `--rank-weight` flag with formatted values:

```bash
pytest --regsmart --rank-weight=0-1
```

- Weights are separated by ``-``
  - The first weight is for running faster tests
  - The second weight is for running recently failed tests
  - The third weight is for running tests more similar to the changed `*.py` files since the last run
- All weights must be integers or floats, and their sum will be normalized to 1
- A higher weight means that a corresponding heuristic is favored.

The default value is ``1-0``, which only prioritizes faster tests.

### Optimizing test prioritization levels

You can set at which level of your test suite will be reordered, by passing the optional `--rank-level` flag in one of these values: `put`, `function`, `module`. For example:

```bash
pytest --regsmart --rank-level=function
```

- The smallest test item that can be reordered in pytest test suite is [parametrized unit test](https://docs.pytest.org/en/7.1.x/example/parametrize.html) (PUT)
- This option allows you to set at which level the reordering takes place:
  - `put` reorders the each PUT and re-arranges their order based on their assigned priority scores
  - `function` reorders each test function, parametrized values of a test function follow their default order
  - `module` reorders each test file, all tests in the test file follow their default order

The default value is `put`.

### Replaying specified test order

You can run/replay tests in a specific order by listing the to-be-run test IDs in a text file, where each line is a test ID, and pass the file path to the optional `--rank-replay` flag:

```bash
pytest --regsmart --rank-replay=replay_order.txt
```

### Tracking data from historical runs

You can also set the maximum value of *the number test runs since a test's last failure* that could be recorded for each test, by passing the optional `--rank-hist-len` flag:

```bash
pytest --regsmart --rank-hist-len=30
```

The default value is 50.
Note that `pytest-regsmart` does not store any historical test run logs, it merely updates its cached data from the previous run with data from the latest run.

### Running tests in random order

You can prompt `pytest-regsmart` to run tests in random order, by setting the sum of `--rank-weight` option to 0, e.g., `--rank-weight=0-0`.
You can also set the seed used when running tests in random order, via setting an integer to the option `--rank-seed`.
For example, the command below runs tests randomly with seed `1234`:

```bash
pytest --regsmart --rank-weight=0-0 --rank-seed=1234
```

By default, `pytest-regsmart` uses `0` as the seed.

### Setting configurable options via config file

You can always apply available options by adding them to the ``addopts`` setting in your [pytest.ini](https://docs.pytest.org/en/latest/reference/customize.html#configuration).

For example, create `pytest.ini` in your codebase root folder as such:

```ini
[pytest]
addopts = --regsmart --rank-weight=0-1 --rank-hist-len=30
```

and run `pytest` on the command line.

Alternatively, you can also create `pytest.ini` in your codebase root folder as such:

```ini
[pytest]
rank_weight=0-1
rank_hist_len=30
```

and run `pytest --regsmart` on the command line.

## How Regression Test Selection (RTS) works

When `--regsmart` is used, `pytest-regsmart` runs a Regression Test Selection step before the tests are executed:

1. **Compute the changed files.** It uses git to inspect the working tree against the **base** branch — the repository's default branch (`main`, or `master` if that is how it is named), never the currently checked-out branch:
   - the base is resolved first as a local `main`/`master` and then as the remote-tracking `origin/main`/`origin/master` — which is what a full checkout (`fetch-depth: 0` in `actions/checkout`) leaves available on a GitHub Actions PR or push;
   - the diff is the working tree vs the merge-base with that base, so every commit on a PR/branch is compared against `main`/`master`, not against itself;
   - it collects both modified (`staged` + `unstaged`) and untracked files. If the repository has no commits yet, only untracked files are considered.

2. **Build a dependency graph when changes exist.** If a diff is detected, [`pyan3`](https://pypi.org/project/pyan3/) parses every `*.py` file in the repository (excluding `.venv`, `venv`, `.git`, `__pycache__`, `dist`, `build`) and builds a dependency graph whose granularity follows `--diff-level`: a function-level call graph when `function` (default), or a module-level import graph when `file`. The graph is then inverted so that, for each node, it knows *which* other nodes depend on it.
3. **Propagate changes transitively.** A BFS traversal starts from the changed units — changed files at the `file` level, or the functions containing the changed lines at the `function` level — and walks through their dependents, collecting every test unit affected directly or indirectly: test files (files named `test_*.py` or `*_test.py`) or individual test functions, respectively.
4. **Filter the test suite.** At the `file` level, test items whose file is not in the selected set are removed; at the `function` level, only collected items matching a selected pytest nodeid are kept. Only affected tests are actually executed.

If there is no diff since the baseline, `pytest-regsmart` skips both dependency-graph generation and test selection, reports a warning, and runs the full test suite. RTP still runs unless `--no-rank` is set; with both no diff and `--no-rank`, the plugin reports that it has no work to do.

Because selection granularity follows `--diff-level`, the default `function` level narrows the selection down to the affected test functions, while `file` selects whole files and is therefore intentionally conservative: a change in one module selects every test file that transitively depends on it, which may include more tests than strictly necessary. See [Choosing the diff granularity](#choosing-the-diff-granularity).

## How Regression Test Prioritization (RTP) works

After selection, `pytest-regsmart` reorders the remaining tests so that failures are exposed sooner. Each test receives a priority score computed as the weighted sum of two heuristics:

- **Faster tests first**, based on their recorded execution durations from previous runs;
- **Recently failed tests first**, based on how many runs have passed since each test's last failure.

Weights are set with `--rank-weight`, normalized to sum 1 (default `1-0`, speed only), and scores are aggregated per group according to `--rank-level` (`put`, `function`, or `module`). Two special modes replace these heuristics: replaying a fixed order listed in a text file (`--rank-replay`) and random order (`--rank-weight=0-0`, seeded by `--rank-seed`). Tests carrying an `order` or `dependency` marker always run first, in their declared order.

See [Usage](#usage) for all available options.

## Deployment (wip)

`pytest-regsmart` is easy to deploy into CI workflow, please see [deployment](./DEPLOYMENT.md).

## Local development

Install the package and dependencies with uv:

```bash
uv sync
```

### Running tests

```bash
uv run pytest -xv tests/
```

To test across all supported Python versions, use [tox](https://tox.readthedocs.io/en/latest/):

```bash
tox
```

To run a specific environment only (e.g. Python 3.12):

```bash
tox -e py312
```

To pass extra arguments to pytest via tox:

```bash
tox -- -k "test_name"
```

## Compatibility

`pytest-regsmart` works with [_pytest_ test filtering](https://docs.pytest.org/en/6.2.x/usage.html#specifying-tests-selecting-tests) and [parallelization](https://pypi.org/project/pytest-xdist).
It also works with plugins for ordering tests, e.g., [pytest-order](https://pypi.org/project/pytest-order), [pytest-dependency](https://pypi.org/project/pytest-dependency) by
running ordered tests first in their declared order.
Pytest options that order tests generally (e.g., [`--ff`](https://docs.pytest.org/en/stable/how-to/cache.html#usage)), or plugins that randomly order tests (e.g., [pytest-randomly](https://github.com/pytest-dev/pytest-randomly), [pytest-random-order](https://github.com/pytest-dev/pytest-random-order), [pytest-reverse](https://github.com/adamchainz/pytest-reverse)), can interfere with `pytest-regsmart` as they use the same reordering hook.

`pytest-regsmart` supports Python 3.10+.

## Reference

#### Demo video
A 5-minute demo video with walkthrough of `pytest-ranking`: [YouTube link](https://youtu.be/SrnkgTs3uok?feature=shared)
(pytest-regsmart: TBA)

#### Bibtex citation

```
@inproceedings{cheng2025pytest,
  title={{pytest-ranking: A Regression Test Prioritization Tool for Python}},
  author={Cheng, Runxiang and Ke, Kaiyao and Marinov, Darko},
  booktitle={Companion Proceedings of the 33rd ACM International Conference on the Foundations of Software Engineering},
  year={2025},
}
```

(pytest-regsmart: TBA)

## Contributing

Contributions are very welcome.

## License

Distributed under the terms of the [GNU General Public License v2.0 or later](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html), `pytest-regsmart` is free and open-source software.
See [NOTICE.md](./NOTICE.md) for attribution of the incorporated third-party code (pytest-ranking under the MIT License and pyan3 under the GPLv2+).

## Issues

If you encounter any problems, please [file an issue](https://github.com/leticosta4/pytest-regsmart/issues) or [pull request](https://github.com/leticosta4/pytest-regsmart/pulls) along with a detailed description.
