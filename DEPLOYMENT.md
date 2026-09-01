# Deployment

## Using pytest-regsmart in fixed location

If your CI runs different test builds in a fixed location, e.g., a project folder in specific machine, you can directly use `pytest-regsmart` after installation without additional setup.

## Using pytest-regsmart in Github Actions

If your CI workflow always starts a new virtual machine to run a test build, you need to set up the CI to be able to pass `pytest` cache data across test builds.
Here, we use GitHub Actions as an example.

### Check out the full history

`pytest-regsmart` computes the diff against the **base** (destination) branch — e.g. `main` for a PR or push. GitHub Actions' default checkout does a shallow, single-branch clone (`fetch-depth: 1`), which does not fetch that base branch, so the base cannot be resolved and `pytest-regsmart` raises a `UsageError`. Fetch the full history:

```yml
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0
```

This only affects the clone metadata, not the working-tree files, so the added time is negligible even for large repositories.

### Add pytest-regsmart to project dependency


You can add `pytest-regsmart` as a dependency by adding a installation job before the job that runs `pytest ...` (a job is often specified by `-name: `) in the workflow file:

```yml
    - name: Install pytest-regsmart related
      run: pip install pytest-regsmart
```

Alternatively, depending on where the forked project puts its dependency, e.g., can be in `setup.py`, `pyproejct.toml`, you can also add the `pytest-regsmart` to the build/test dependency, but best not to specify version.

If `pytest-regsmart` is not published on PyPI yet, install it from the repository branch: `pip install "pytest-regsmart @ git+https://github.com/leticosta4/pytest-regsmart.git@main"` (or pin it in `pyproject.toml`/`requirements.txt` the same way, so `uv sync` picks it up).


#### If the project uses `Tox`

Add `pytest-regsmart` to the `deps` of `[testenv]` in `./tox.ini`:
```ini
[testenv]
deps =
  ; ...
  pytest-regsmart
  pytest-json-report
```


### Setup pytest_cache

Before the job in the workflow file that runs the `pytest ...` but after the `pytest-regsmart` installation job, add the job that restores cache from the latest run if such run exists:

```yml
    - name: Restore pytest-regsmart cache
      id: restore-pytest-regsmart-cache
      if: always()
      uses: actions/cache/restore@v4
      with:
        path: ${{ github.workspace }}/.pytest_cache/v/pytest_ranked_selection_data
        key: pytest-regsmart-cache-${{ github.workflow }}-${{ runner.os }}-${{ matrix.python }}
        restore-keys: |
          pytest-regsmart-cache-${{ github.workflow }}-${{ runner.os }}-${{ matrix.python }}
    # --------below is the job for running pytest
    -name: pytest
        ...
```

And after the job that runs `pytest ...` command, add the job that caches result of this run:

```yml
    -name: pytest
        ...
    # --------above is the job for running pytest
    - name: Save pytest-regsmart cache
      id: save-pytest-regsmart-cache
      if: always()
      uses: actions/cache/save@v4
      with:
        path: ${{ github.workspace }}/.pytest_cache/v/pytest_ranked_selection_data
        key: pytest-regsmart-cache-${{ github.workflow }}-${{ runner.os }}-${{ matrix.python }}-${{ github.run_id }}
```

#### If the project uses `Tox`

You need to manually identify the location of `./pytest_cache` folder when tox is used by inspecting the workflow run log, it looks like this:
```
============================= test session starts ==============================
...
cachedir: .tox/TOX_ENV_NAME/.pytest_cache
...
```

The `cachedir` is what we are looking for. In this example, we need to replace `path: ${{ github.workspace }}/.pytest_cache/v/pytest_ranked_selection_data` into `path: ${{ github.workspace }}/.tox/TOX_ENV_NAME/v/pytest_ranked_selection_data` in both the `restore` and `save` cache jobs above in the workflow file.

#### Alternative to `actions/cache`

[`actions/cache`](https://github.com/actions/cache) is one way to allow data from a previous GutHub Actions CI build to be used in the future build.
One limitation of `actions/cache` is that its cache has a retention period and the total size of all caches for a repository is limited ([reference](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows#usage-limits-and-eviction-policy)).


One can also setup a more stable cache storage, e.g., a remote server, and use other GitHub actions to transfer cache data from/to a specific destination. Example actions are [`scp-action`](https://github.com/appleboy/scp-action) and [`copy-via-ssh`](https://github.com/marketplace/actions/copy-via-ssh)
