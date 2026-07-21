# pytest-regsmart

A Pytest plugin that implements Regression Test Prioritization (RTP) for faster regression fault detection.

This [pytest](https://github.com/pytest-dev/pytest) plugin allows you to find regression test failures faster and receive testing feedback sooner from CI build.
It speeds up the failure detection of your test suite by executing earlier the tests that are faster and recently failed.

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
You can run `pytest-regsmart` with its default configuration, which runs faster tests first by passing the ``--rank`` option:

```bash
pytest --rank
```

Before the test run starts, if `--rank` is passed, the terminal header will report `pytest-regsmart`'s configuration of this run, for example:

```
Using --rank-weight=1-0
Using --rank-level=put
Using --rank-hist-len=50
Using --rank-seed=123
Using --rank-replay=None
```

After the test run finishes, the terminal summary will show the overhead of `pytest-regsmart` in this run, for example:

```
=================================== pytest-regsmart summary info ====================================
Time to reorder tests (s): 0.0003600120544433594
Time to collect test features (s): 0.0004608631134033203
```

### Optimizing test prioritization heuristics

You can set the weights of different test prioritization heuristics by passing the optional `--rank-weight` flag with formatted values:

```bash
pytest --rank --rank-weight=0-1
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
pytest --rank --rank-level=function
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
pytest --rank --rank-replay=replay_order.txt
```

### Tracking data from historical runs

You can also set the maximum value of *the number test runs since a test's last failure* that could be recorded for each test, by passing the optional `--rank-hist-len` flag:

```bash
pytest --rank --rank-hist-len=30
```

The default value is 50.
Note that `pytest-regsmart` does not store any historical test run logs, it merely updated its cached data from the previous run with data from the latest run.

### Running tests in random order

You can prompt `pytest-regsmart` to run tests in random order, by setting the sum of `--rank-weight` option to 0, e.g., `--rank-weight=0-0`.
You can also set the seed used when running tests in random order, via setting an integer to the option `--rank-seed`.
For example, the command below runs tests randomly with seed `1234`:

```bash
pytest --rank --rank-weight=0-0 --rank-seed=1234
```

By default, `pytest-regsmart` uses `0` as the seed.

### Setting configurable options via config file

You can always apply available options by adding them to the ``addopts`` setting in your [pytest.ini](https://docs.pytest.org/en/latest/reference/customize.html#configuration).

For example, create `pytest.ini` in your codebase root folder as such:

```ini
[pytest]
addopts = --rank --rank-weight=0-1 --rank-hist-len=30
```

and run `pytest` on the command line.

Alternatively, you can also create `pytest.ini` in your codebase root folder as such:

```ini
[pytest]
rank_weight=0-1
rank_hist_len=30
```

and run `pytest --rank` on the command line.

## Deployment (old)

`pytest-ranking` is easy to deploy into CI workflow, please see [deployment](./docs/DEPLOYMENT.md).

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

`pytest-regsmart` works with [test selection](https://docs.pytest.org/en/6.2.x/usage.html#specifying-tests-selecting-tests) and [parallelization](https://pypi.org/project/pytest-xdist).
It also works with plugins for ordering tests, e.g., [pytest-order](https://pypi.org/project/pytest-order), [pytest-dependency](https://pypi.org/project/pytest-dependency) by
running ordered tests first in their declared order.
Pytest options that order tests generally (e.g., [`--ff`](https://docs.pytest.org/en/stable/how-to/cache.html#usage)), or plugins that randomly order tests (e.g., [pytest-randomly](https://github.com/pytest-dev/pytest-randomly), [pytest-random-order](https://github.com/pytest-dev/pytest-random-order), [pytest-reverse](https://github.com/adamchainz/pytest-reverse)), can interfere with `pytest-regsmart` as they use the same reordering hook.

## Reference

#### Demo video
A 5-minute demo video with walkthrough of `pytest-ranking`: [YouTube link](https://youtu.be/SrnkgTs3uok?feature=shared)

#### Bibtex citation

```
@inproceedings{cheng2025pytest,
  title={{pytest-ranking: A Regression Test Prioritization Tool for Python}},
  author={Cheng, Runxiang and Ke, Kaiyao and Marinov, Darko},
  booktitle={Companion Proceedings of the 33rd ACM International Conference on the Foundations of Software Engineering},
  year={2025},
}
```

## Contributing

Contributions are very welcome.

## License

Distributed under the terms of the [MIT](http://opensource.org/licenses/MIT) license, `pytest-regsmart` is free and open-source software.

## Issues

If you encounter any problems, please [file an issue](https://github.com/leticosta4/pytest-regsmart/issues) or [pull request](https://github.com/leticosta4/pytest-regsmart/pulls) along with a detailed description.
