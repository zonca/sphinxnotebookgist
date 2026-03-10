# Repository Guidelines

## Project Structure & Module Organization
`sphinxnotebookgist/` contains the package code. The extension currently lives in [`sphinxnotebookgist/__init__.py`](/home/zonca/p/software/sphinxnotebookgist/sphinxnotebookgist/__init__.py), including URL resolution, notebook fetching, source comparison, and Sphinx event hooks. `tests/` holds the test suite: [`tests/test_unit.py`](/home/zonca/p/software/sphinxnotebookgist/tests/test_unit.py) covers pure functions, while [`tests/test_integration.py`](/home/zonca/p/software/sphinxnotebookgist/tests/test_integration.py) runs end-to-end Sphinx builds. `tests/fixtures/` stores sample notebooks used by both suites.

## Build, Test, and Development Commands
Install a local dev environment with:

```bash
python -m pip install -e '.[dev]'
```

Run the full test suite with:

```bash
pytest
```

Run a focused file while iterating:

```bash
pytest tests/test_unit.py
pytest tests/test_integration.py
```

If you need a distribution artifact, use `python -m build` after installing the `build` package locally.

## Coding Style & Naming Conventions
Target Python 3.9+ and follow PEP 8 with 4-space indentation. Keep functions small and explicit; this package favors straightforward standard-library code over extra abstractions. Use `snake_case` for functions and variables, `UPPER_CASE` for module constants, and `Test...` classes with `test_...` methods in pytest. Preserve the existing docstring-heavy style for public behavior and error cases.

## Testing Guidelines
Use `pytest` for all tests. Add unit tests for helper logic such as URL parsing or notebook comparison, and integration tests for Sphinx lifecycle behavior and filesystem side effects. Name new tests by behavior, for example `test_gist_url_api_error_raises`. Prefer fixtures under `tests/fixtures/` when sample notebooks are needed. No formal coverage gate is configured, but new behavior should ship with direct test coverage.

## Commit & Pull Request Guidelines
Recent commits use short, imperative subjects such as `Implement sphinxnotebookgist Sphinx extension with tests`. Follow that pattern and keep the first line specific. Pull requests should describe the behavior change, list the tests run, and link any related issue. Include notebook or Sphinx build examples when the change affects contributor workflow or rendered output.
