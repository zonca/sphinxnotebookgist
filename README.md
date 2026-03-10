# sphinxnotebookgist

`sphinxnotebookgist` is a Sphinx extension that replaces source-only Jupyter notebooks with executed notebook files during the Sphinx build, after first verifying that the cell sources still match.

## What It Does
- Scans `.ipynb` files under the Sphinx source directory.
- Looks for `metadata.sphinxnotebookgist.url`.
- Resolves GitHub Gist page URLs to the raw notebook file.
- Compares local and fetched notebook cell sources.
- Replaces the local notebook in place when the sources match.

This allows repositories to keep clean notebooks without outputs while still rendering executed outputs in tools such as `nbsphinx` or `myst-nb`.

## Example Metadata

```json
{
  "metadata": {
    "sphinxnotebookgist": {
      "url": "https://gist.github.com/<user>/<gist_id>"
    }
  }
}
```

Supported URLs include GitHub Gist page URLs, direct `http(s)` raw notebook URLs, and local `file://` URLs for testing.

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

Run a focused suite with `pytest tests/test_unit.py` or `pytest tests/test_integration.py`.

## Contributing

Contributor workflow, coding style, and test expectations are documented in [`AGENTS.md`](AGENTS.md).
