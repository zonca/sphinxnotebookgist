"""Integration tests for sphinxnotebookgist.

These tests run a real Sphinx build to verify the end-to-end behaviour of the
extension.  The executed notebook fixture lives in ``tests/fixtures/`` and is
referenced via a ``file://`` URL so no network access is required.
"""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest
from sphinx.application import Sphinx
from sphinx.errors import ExtensionError

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_notebook(executed_url: str) -> dict:
    """Return a notebook whose cells match *executed_notebook.ipynb* but have
    no outputs, and whose metadata points to *executed_url*."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "sphinxnotebookgist": {
                "url": executed_url,
            },
        },
        "cells": [
            {
                "cell_type": "markdown",
                "id": "md-cell-1",
                "metadata": {},
                "source": "# Test Notebook\n\nThis notebook is used for testing sphinxnotebookgist.",
            },
            {
                "cell_type": "code",
                "id": "code-cell-1",
                "execution_count": None,
                "metadata": {},
                "source": 'print("hello from sphinxnotebookgist")',
                "outputs": [],
            },
            {
                "cell_type": "code",
                "id": "code-cell-2",
                "execution_count": None,
                "metadata": {},
                "source": "2 + 2",
                "outputs": [],
            },
        ],
    }


def _make_different_notebook(executed_url: str) -> dict:
    """Return a notebook whose cells do NOT match *executed_notebook.ipynb*."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "sphinxnotebookgist": {
                "url": executed_url,
            },
        },
        "cells": [
            {
                "cell_type": "code",
                "id": "code-cell-1",
                "execution_count": None,
                "metadata": {},
                "source": 'print("this is completely different")',
                "outputs": [],
            },
        ],
    }


def _setup_sphinx_project(srcdir: Path, nb_data: dict) -> None:
    """Write a minimal Sphinx project to *srcdir*."""
    # conf.py – load only sphinxnotebookgist (no notebook renderer needed
    # because we just test the builder-inited event, not HTML output)
    (srcdir / "conf.py").write_text(
        "extensions = ['sphinxnotebookgist']\n"
        "master_doc = 'index'\n"
    )

    # index.rst
    (srcdir / "index.rst").write_text(
        "Test\n"
        "====\n\n"
        ".. toctree::\n"
        "   :maxdepth: 1\n"
    )

    # Write the notebook
    nb_path = srcdir / "notebook.ipynb"
    with nb_path.open("w") as fh:
        json.dump(nb_data, fh, indent=1)
        fh.write("\n")


def _run_sphinx(srcdir: Path, outdir: Path, doctreedir: Path) -> Sphinx:
    """Build a Sphinx project; raises on error."""
    status = io.StringIO()
    warning = io.StringIO()
    app = Sphinx(
        srcdir=str(srcdir),
        confdir=str(srcdir),
        outdir=str(outdir),
        doctreedir=str(doctreedir),
        buildername="html",
        status=status,
        warning=warning,
    )
    app.build()
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIntegrationSuccess:
    """The extension replaces the local notebook with the executed version."""

    def test_notebook_replaced_with_executed_version(self, tmp_path):
        srcdir = tmp_path / "src"
        srcdir.mkdir()

        executed_url = (FIXTURES / "executed_notebook.ipynb").as_uri()
        nb_data = _make_source_notebook(executed_url)
        _setup_sphinx_project(srcdir, nb_data)

        _run_sphinx(
            srcdir,
            tmp_path / "out",
            tmp_path / "doctrees",
        )

        # After the build the notebook file should have been replaced
        with (srcdir / "notebook.ipynb").open() as fh:
            result_nb = json.load(fh)

        # The executed notebook has outputs; the source one did not.
        code_cells = [c for c in result_nb["cells"] if c["cell_type"] == "code"]
        assert any(
            len(c.get("outputs", [])) > 0 for c in code_cells
        ), "Notebook was not replaced with the executed version"

    def test_notebook_without_metadata_is_skipped(self, tmp_path):
        """A notebook without sphinxnotebookgist metadata is left alone."""
        srcdir = tmp_path / "src"
        srcdir.mkdir()

        nb_without_meta = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "source": "x = 1",
                    "outputs": [],
                    "execution_count": None,
                    "metadata": {},
                }
            ],
        }
        _setup_sphinx_project(srcdir, nb_without_meta)

        _run_sphinx(
            srcdir,
            tmp_path / "out",
            tmp_path / "doctrees",
        )

        # File should be unchanged (the extension should not have touched it)
        result_text = (srcdir / "notebook.ipynb").read_text()
        # Compare parsed JSON to avoid whitespace issues
        assert json.loads(result_text) == nb_without_meta

    def test_checkpoint_notebooks_are_skipped(self, tmp_path):
        """Notebooks inside .ipynb_checkpoints are never processed."""
        srcdir = tmp_path / "src"
        srcdir.mkdir()

        # Set up the project without any notebook in srcdir (no top-level nb)
        (srcdir / "conf.py").write_text(
            "extensions = ['sphinxnotebookgist']\n"
            "master_doc = 'index'\n"
        )
        (srcdir / "index.rst").write_text("Test\n====\n")

        # Place a "broken" notebook inside a checkpoints directory
        ckpt_dir = srcdir / ".ipynb_checkpoints"
        ckpt_dir.mkdir()
        bad_nb = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "sphinxnotebookgist": {"url": "https://example.com/nonexistent.ipynb"}
            },
            "cells": [],
        }
        with (ckpt_dir / "notebook-checkpoint.ipynb").open("w") as fh:
            json.dump(bad_nb, fh)

        # Should succeed without trying to fetch the URL
        _run_sphinx(
            srcdir,
            tmp_path / "out",
            tmp_path / "doctrees",
        )


class TestIntegrationFailure:
    """The extension halts the build when source cells differ."""

    def test_different_source_raises_extension_error(self, tmp_path):
        srcdir = tmp_path / "src"
        srcdir.mkdir()

        executed_url = (FIXTURES / "executed_notebook.ipynb").as_uri()
        nb_data = _make_different_notebook(executed_url)
        _setup_sphinx_project(srcdir, nb_data)

        with pytest.raises(ExtensionError, match="differs from the executed version"):
            _run_sphinx(
                srcdir,
                tmp_path / "out",
                tmp_path / "doctrees",
            )

    def test_unreachable_url_raises_extension_error(self, tmp_path):
        srcdir = tmp_path / "src"
        srcdir.mkdir()

        nb_data = _make_source_notebook("file:///nonexistent/path/notebook.ipynb")
        _setup_sphinx_project(srcdir, nb_data)

        with pytest.raises(ExtensionError, match="failed to fetch notebook"):
            _run_sphinx(
                srcdir,
                tmp_path / "out",
                tmp_path / "doctrees",
            )
