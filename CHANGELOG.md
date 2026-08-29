
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] pytest-regsmart

## [0.6.3] - 2026-08-29
 
### Added
- Add validation for args options in pytest.ini
- Add default values for diff-level, rank-level and no-rank flags in pytest.ini
## [0.6.2] - 2026-08-22
 
### Added
- New `--diff-level` flag to choose the diff granularity: `function`pr (default) or `file`
- Track deleted files in the diff result
## [0.6.1] - 2026-08-11
 
### Changed
- License changed from MIT to GPLv2+
### Added
- Default branch information in summary log report
## [0.6.0] - 2026-08-10
 
### Security
- Bump pytest from version 7.4.3 to 9.0.3 ([CVE-2025-71176](https://github.com/leticosta4/pytest-regsmart/security/dependabot/1))
- Bump gitpython from 3.1.57 to 3.1.58 ([CVEs](https://github.com/leticosta4/pytest-regsmart/security/dependabot?q=GitPython+is%3Aclosed))
### Removed
- Support for Python 3.8 and 3.9
## [0.5.0] - 2026-08-07
 
### Added
- Regression Test Selection (RTS): a new `selection` module that computes the test files affected by the current changes and runs only them under `--regsmart`
  - Detect changed files with git (modified + untracked) against the resolved default branch (origin/HEAD → main/master → active branch); repositories without commits fall back to untracked files only
  - Build a module-level dependency graph with pyan3 and propagate changes transitively (BFS) to affected test files
  - Raise a `UsageError` when `--regsmart` is used outside a git repository
- Report the RTS configuration and timing in the terminal header/summary
- Integration tests for the selection module and improved test suite
### Changed
- Refine `--no-rank`: it now only disables RTP while keeping RTS active, and cannot be combined with other `--rank-*` flags (raises a `UsageError`)
## [0.4.0] - 2026-07-24
 
### Added
- `--no-rank` option to remove RTP, considering only the future RTS module
### Changed
- Rename activation flag from `--rank` to `--regsmart`
- Improve documentation
## [0.3.0] - 2026-07-20
 
### Changed
- Migrate package manager to uv
## [0.2.0] - 2026-07-19
 
### Changed
- Rename whole package name to `pytest-regsmart`
- Refactor ranking module internals (modularization)
### Removed
- Directory-level granularity (`--rank-level=dir`)
## [0.1.0] - 2026-06-25
 
### Added
- Fork of pytest-ranking (based on PyPI release 0.3.4)
### Changed
- Rename plugin to `pytest-regsmart`
### Removed
- Similar Changed Path method (`--rank-weight=0-0-1`)

---

## Inherited history (pytest-ranking)

## [0.3.4] - 2025-04-09
 
### Added
- Replay option
- Published version at [PyPI](https://pypi.org/project/pytest-ranking/0.3.4/#history)
### Changed
- Refine random order and test group level
- Code refactoring
## [0.3.3] - 2024-12-24
 
### Added
- Support order dependency
## [0.3.2] - 2024-12-23
 
### Changed
- Refine test group level definition and extraction
- Use pytest test discovery order as default
## [0.3.1] - 2024-06-06
 
### Added
- Support ranking tests at different granularity levels (PUT, method, file, folder)
- Plugin summary via `pytest_terminal_summary`
## [0.3.0] - 2024-05-12
 
### Fixed
- Attribute initialization in change tracker for Python 3.11 and lower versions
## [0.2.8] - 2024-05-08
 
### Fixed
- pytest-xdist compatibility for random and change-related heuristics
## [0.2.7] - 2024-03-18
 
### Added
- Option to run tests in random order
### Changed
- Improve documentation
## [0.2.0] - 2024-02-16
 
### Added
- Textual similarity between tests and changed files since last run as the third heuristic
- History length as an optional argument
### Changed
- Weight normalization
- Rename plugin to `pytest-ranking`
## [0.1.0] - 2023-12-04
 
### Added
- First release on PyPI
