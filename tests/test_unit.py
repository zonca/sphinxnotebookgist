"""Unit tests for sphinxnotebookgist core functions."""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sphinxnotebookgist import (
    ExtensionError,
    fetch_notebook,
    get_cell_sources,
    resolve_url,
    sources_match,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_notebook(*cells: tuple[str, str], **kwargs) -> dict:
    """Build a minimal notebook dict from (cell_type, source) pairs."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": kwargs.get("metadata", {}),
        "cells": [
            {
                "cell_type": ct,
                "source": src,
                "metadata": {},
                "outputs": [],
                "execution_count": None,
            }
            for ct, src in cells
        ],
    }


# ---------------------------------------------------------------------------
# resolve_url
# ---------------------------------------------------------------------------


class TestResolveUrl:
    def test_non_gist_url_returned_unchanged(self):
        url = "https://raw.githubusercontent.com/user/repo/main/nb.ipynb"
        assert resolve_url(url) == url

    def test_file_url_returned_unchanged(self):
        url = "file:///tmp/notebook.ipynb"
        assert resolve_url(url) == url

    def test_raw_gist_url_returned_unchanged(self):
        url = "https://gist.githubusercontent.com/user/abc123/raw/commit/nb.ipynb"
        assert resolve_url(url) == url

    def test_gist_page_url_calls_api(self):
        gist_id = "abc123def456abc1"
        url = f"https://gist.github.com/user/{gist_id}"
        raw_url = "https://gist.githubusercontent.com/user/abc123/raw/HASH/notebook.ipynb"
        api_response = {
            "files": {
                "notebook.ipynb": {
                    "filename": "notebook.ipynb",
                    "raw_url": raw_url,
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(api_response).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            result = resolve_url(url)

        assert result == raw_url
        called_url = mock_open.call_args[0][0].full_url
        assert f"api.github.com/gists/{gist_id}" in called_url

    def test_gist_url_trailing_slash(self):
        gist_id = "abc123def456abc1"
        url = f"https://gist.github.com/user/{gist_id}/"
        raw_url = "https://gist.githubusercontent.com/user/abc123/raw/HASH/nb.ipynb"
        api_response = {
            "files": {
                "nb.ipynb": {
                    "filename": "nb.ipynb",
                    "raw_url": raw_url,
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(api_response).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = resolve_url(url)

        assert result == raw_url

    def test_gist_url_no_ipynb_raises(self):
        gist_id = "abc123def456abc1"
        url = f"https://gist.github.com/user/{gist_id}"
        api_response = {"files": {"readme.md": {"raw_url": "https://example.com/readme.md"}}}
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(api_response).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(ExtensionError, match="no .ipynb file found"):
                resolve_url(url)

    def test_gist_url_api_error_raises(self):
        url = "https://gist.github.com/user/abc123def456abc1"
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with pytest.raises(ExtensionError, match="failed to query GitHub API"):
                resolve_url(url)


# ---------------------------------------------------------------------------
# fetch_notebook
# ---------------------------------------------------------------------------


class TestFetchNotebook:
    def test_fetch_valid_json(self):
        nb = _make_notebook(("code", "x = 1"))
        raw = json.dumps(nb).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = raw

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_notebook("https://example.com/nb.ipynb")

        assert result["cells"][0]["source"] == "x = 1"

    def test_fetch_url_error_raises(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("not found"),
        ):
            with pytest.raises(ExtensionError, match="failed to fetch notebook"):
                fetch_notebook("https://example.com/missing.ipynb")

    def test_fetch_invalid_json_raises(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b"not json"

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(ExtensionError, match="not valid JSON"):
                fetch_notebook("https://example.com/bad.ipynb")

    def test_fetch_from_file_url(self):
        executed_path = FIXTURES / "executed_notebook.ipynb"
        result = fetch_notebook(executed_path.as_uri())
        assert "cells" in result
        # Should have outputs in the executed notebook
        code_cells = [c for c in result["cells"] if c["cell_type"] == "code"]
        assert any(len(c["outputs"]) > 0 for c in code_cells)


# ---------------------------------------------------------------------------
# get_cell_sources
# ---------------------------------------------------------------------------


class TestGetCellSources:
    def test_basic_extraction(self):
        nb = _make_notebook(("markdown", "# Hello"), ("code", "x = 1"))
        sources = get_cell_sources(nb)
        assert sources == [("markdown", "# Hello"), ("code", "x = 1")]

    def test_source_as_list_is_joined(self):
        nb = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["line1\n", "line2\n", "line3"],
                    "outputs": [],
                }
            ]
        }
        sources = get_cell_sources(nb)
        assert sources == [("code", "line1\nline2\nline3")]

    def test_empty_notebook(self):
        nb = {"cells": []}
        assert get_cell_sources(nb) == []

    def test_no_cells_key(self):
        assert get_cell_sources({}) == []

    def test_outputs_are_ignored(self):
        nb = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": "print('hi')",
                    "outputs": [{"output_type": "stream", "text": "hi\n"}],
                    "execution_count": 5,
                }
            ]
        }
        sources = get_cell_sources(nb)
        assert sources == [("code", "print('hi')")]


# ---------------------------------------------------------------------------
# sources_match
# ---------------------------------------------------------------------------


class TestSourcesMatch:
    def test_identical_notebooks_match(self):
        nb = _make_notebook(("markdown", "# Hello"), ("code", "x = 1"))
        assert sources_match(nb, nb) is True

    def test_same_source_different_outputs_match(self):
        source_nb = _make_notebook(("code", "print('hi')"))
        executed_nb = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "source": "print('hi')",
                    "outputs": [{"output_type": "stream", "text": "hi\n"}],
                    "execution_count": 1,
                    "metadata": {},
                }
            ],
        }
        assert sources_match(source_nb, executed_nb) is True

    def test_different_source_does_not_match(self):
        nb_a = _make_notebook(("code", "x = 1"))
        nb_b = _make_notebook(("code", "y = 2"))
        assert sources_match(nb_a, nb_b) is False

    def test_different_cell_count_does_not_match(self):
        nb_a = _make_notebook(("code", "x = 1"))
        nb_b = _make_notebook(("code", "x = 1"), ("code", "y = 2"))
        assert sources_match(nb_a, nb_b) is False

    def test_different_cell_type_does_not_match(self):
        nb_a = _make_notebook(("code", "hello"))
        nb_b = _make_notebook(("markdown", "hello"))
        assert sources_match(nb_a, nb_b) is False

    def test_list_source_matches_string_source(self):
        nb_a = {
            "cells": [{"cell_type": "code", "source": ["line1\n", "line2"], "outputs": []}]
        }
        nb_b = {
            "cells": [{"cell_type": "code", "source": "line1\nline2", "outputs": []}]
        }
        assert sources_match(nb_a, nb_b) is True

    def test_fixture_executed_matches_itself(self):
        with open(FIXTURES / "executed_notebook.ipynb") as fh:
            nb = json.load(fh)
        assert sources_match(nb, nb) is True

    def test_fixture_different_does_not_match_executed(self):
        with open(FIXTURES / "executed_notebook.ipynb") as fh:
            executed = json.load(fh)
        with open(FIXTURES / "different_notebook.ipynb") as fh:
            different = json.load(fh)
        assert sources_match(different, executed) is False
