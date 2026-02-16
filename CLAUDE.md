# CLAUDE.md

Guide for AI assistants working with the looptime codebase.

## Project Overview

`looptime` is a pytest plugin that fast-forwards asyncio event loop time during tests. It allows tests that `await asyncio.sleep(60)` to complete in near-zero real time while the loop's internal clock advances as if the time actually passed. Zero runtime dependencies; Python 3.10+.

## Repository Layout

```
looptime/                  # Main package (public API in __init__.py)
  _internal/               # All implementation lives here
    loops.py               # Core: LoopTimeEventLoop class, exceptions
    patchers.py            # Event loop class mutation and caching
    plugin.py              # pytest plugin: fixtures, CLI options, hooks
    enabler.py             # enabled() context manager / decorator
    chronometers.py        # Chronometer (wall-clock measurement)
    timeproxies.py         # LoopTimeProxy (numeric proxy to loop.time())
    math.py                # Numeric ABC for float-free arithmetic
tests/                     # pytest test suite
docs/                      # Sphinx documentation (RST)
.github/workflows/         # CI (ci.yaml, thorough.yaml, publish.yaml)
```

## Development Setup

```bash
# Install dev dependencies (editable mode)
pip install --group dev -e .

# Install lint dependencies (includes dev)
pip install --group lint -e .

# Install docs dependencies
pip install --group docs -e .
```

All dependency management is in `pyproject.toml` using PEP 735 dependency groups. There are no `requirements.txt` files.

## Common Commands

### Running Tests

```bash
# Standard test run with coverage
pytest --color=yes --cov=looptime --cov-branch

# Without coverage (faster, used for PyPy)
pytest --color=yes --no-cov
```

### Linting and Type Checking

```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Type check (strict mode)
mypy looptime --strict
```

### Building Documentation

```bash
# From the docs/ directory
sphinx-build -b dirhtml docs/ docs/_build/
```

## Code Architecture

### Public API vs Internal Implementation

All implementation lives in `looptime/_internal/`. The public API is re-exported through `looptime/__init__.py`. Never import directly from `_internal` in external code.

### Key Design Decisions

- **Integer arithmetic for time**: All loop time math uses integer representation (scaled by `resolution_reciprocal`) to avoid floating-point precision errors. See `_internal/math.py`.
- **Class mutation via `__class__`**: Event loops are upgraded by reassigning their `__class__` to a cached subclass mixing in `LoopTimeEventLoop`. No new loop objects are created.
- **Selector interception**: The loop's selector `.select()` is replaced at the instance level to intercept I/O waits and fast-forward fake time.
- **Patch-always, activate-on-demand**: All pytest-asyncio event loops are patched at creation (inactive), then activated only during the specific test's execution.
- **No-op cycle throttling**: The loop runs N no-op cycles (default 42) before advancing the fake clock, preventing timeout contexts from firing prematurely.

### Pytest Plugin Entry Points

Registered in `pyproject.toml` under `[project.entry-points.pytest11]`:
- `looptime_plugin` — core plugin (fixtures, CLI args, hooks)
- `looptime_timeproxies` — `looptime` fixture
- `looptime_chronometers` — `chronometer` fixture

## Code Style and Conventions

### Formatting

- **No auto-formatter** (no black, no ruff). Double-quote string fixer is explicitly disabled.
- **isort** for import sorting: `line_length=120`, `multi_line_output=11`, `balanced_wrapping=true`, `combine_as_imports=true`, `case_sensitive=true`.
- Imports should be sorted with isort. Run `isort .` or rely on pre-commit.

### Type Checking

- **mypy in strict mode** (`mypy looptime --strict`).
- Package ships a `py.typed` marker (PEP 561).
- `mypy` config: `warn_unused_configs = true`, `ignore_missing_imports = true`.

### Pre-commit Hooks

Configured in `.pre-commit-config.yaml`. Key checks include:
- AST validation, trailing whitespace, end-of-file fixers
- TOML/YAML/JSON validation
- No `eval()`, no blanket `noqa`, no `log.warn()`
- Test files must match `test_*.py` pattern (Django-style `--django` flag)
- isort import ordering

### Commit Style

Commit messages are short imperative sentences describing the change. Examples from the repo:
- "Use the original clock if not enabled"
- "Restructure & rewrite the docs for clarity"
- "Add the loop time enabler for explicit usage"
- "Move project configs to pyproject.toml"

## Testing Conventions

- Tests use `pytest` with `pytest-asyncio`.
- `tests/conftest.py` provides an autouse `_clear_caches` fixture that calls `looptime.reset_caches()` before and after each test.
- `test_plugin.py` uses pytest's `pytester` fixture for end-to-end plugin testing.
- Test files are named `test_*.py` and test functions `test_*`.

## Versioning and Releases

- Version is derived from git tags via `setuptools-scm`. The file `looptime/_version.py` is auto-generated and git-ignored.
- Releases are created via GitHub Releases, which trigger the `publish.yaml` workflow to build and publish to PyPI using trusted publishing (OIDC).

## CI Matrix

- **Linters**: Python 3.14, runs pre-commit + mypy strict
- **Unit tests**: Python 3.10, 3.11, 3.12, 3.13, 3.14 (CPython), plus a 3.14 variant with `pytest-asyncio<1.0.0` for legacy compat
- **PyPy tests**: PyPy 3.10, 3.11 (no coverage — poor performance with tracing)
- Coverage published to Coveralls and Codecov
