"""
sphinxnotebookgist
==================

A Sphinx extension that validates and replaces empty Jupyter notebooks with
their executed counterparts during the build process.

Workflow
--------
1. During ``builder-inited``, the extension scans the Sphinx source directory
   for every ``.ipynb`` file that contains a ``sphinxnotebookgist.url`` entry
   in the notebook-level metadata.
2. The executed notebook is fetched from that URL (a GitHub Gist page, a raw
   URL, a ``file://`` path, or any other HTTP(S) URL).
3. The *source cells* (cell type + source text) of the local notebook are
   compared with the fetched one.  Outputs, execution counts, and cell
   metadata are intentionally ignored so that the in-repo file can be stored
   without outputs.
4. If the sources differ an :class:`sphinx.errors.ExtensionError` is raised,
   halting the build so the developer can reconcile the differences.
5. If the sources match, the local file is **replaced in-place** with the
   fully-executed notebook so that downstream Sphinx extensions (e.g.
   *nbsphinx*, *myst-nb*) can render the outputs.

Notebook metadata format
------------------------
Add the following to the top-level ``metadata`` object of the notebook::

    {
      "metadata": {
        "sphinxnotebookgist": {
          "url": "https://gist.github.com/<user>/<gist_id>"
        }
      }
    }

Supported URL schemes
---------------------
* ``https://gist.github.com/<user>/<gist_id>`` – the extension calls the
  GitHub Gist API to resolve the first ``.ipynb`` file in the gist.
* Any other HTTP/HTTPS URL – fetched directly (must return raw JSON).
* ``file:///absolute/path/to/notebook.ipynb`` – useful for local testing.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from sphinx.application import Sphinx
from sphinx.errors import ExtensionError

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_GIST_HTML_RE = re.compile(
    r"https://gist\.github\.com/(?P<user>[^/]+)/(?P<gist_id>[0-9a-f]+)/?$",
    re.IGNORECASE,
)


def resolve_url(url: str) -> str:
    """Return a URL that can be fetched directly as raw notebook JSON.

    For GitHub Gist *page* URLs the GitHub REST API is used to discover the
    raw download URL of the first ``.ipynb`` file in the gist.  All other
    URLs are returned unchanged.

    Parameters
    ----------
    url:
        The URL specified in the notebook metadata.

    Returns
    -------
    str
        A URL whose response body is the raw notebook JSON.

    Raises
    ------
    ExtensionError
        When the GitHub API cannot be reached or the gist contains no
        ``.ipynb`` file.
    """
    m = _GIST_HTML_RE.match(url.strip())
    if m is None:
        # Not a Gist page URL – use as-is (raw gist, HTTPS, file://, …)
        return url

    gist_id = m.group("gist_id")
    api_url = f"https://api.github.com/gists/{gist_id}"

    try:
        req = urllib.request.Request(
            api_url,
            headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req) as resp:
            gist_data: dict[str, Any] = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise ExtensionError(
            f"sphinxnotebookgist: failed to query GitHub API for gist {gist_id!r}: {exc}"
        ) from exc

    for filename, file_info in gist_data.get("files", {}).items():
        if filename.endswith(".ipynb"):
            raw_url: str = file_info["raw_url"]
            return raw_url

    raise ExtensionError(
        f"sphinxnotebookgist: no .ipynb file found in gist {url!r}"
    )


# ---------------------------------------------------------------------------
# Notebook fetching
# ---------------------------------------------------------------------------


def fetch_notebook(url: str) -> dict[str, Any]:
    """Fetch a notebook from *url* and return it as a parsed dictionary.

    Parameters
    ----------
    url:
        A raw URL (HTTP/HTTPS or ``file://``) that points to a notebook JSON
        file.  Pass the result of :func:`resolve_url` when starting from a
        Gist page URL.

    Returns
    -------
    dict
        Parsed notebook dictionary.

    Raises
    ------
    ExtensionError
        When the URL cannot be fetched or the response is not valid JSON.
    """
    try:
        with urllib.request.urlopen(url) as resp:
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise ExtensionError(
            f"sphinxnotebookgist: failed to fetch notebook from {url!r}: {exc}"
        ) from exc

    try:
        notebook: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtensionError(
            f"sphinxnotebookgist: response from {url!r} is not valid JSON: {exc}"
        ) from exc

    return notebook


# ---------------------------------------------------------------------------
# Notebook comparison
# ---------------------------------------------------------------------------


def _normalise_source(source: str | list[str]) -> str:
    """Return a single string regardless of whether *source* is a list."""
    if isinstance(source, list):
        return "".join(source)
    return source


def get_cell_sources(notebook: dict[str, Any]) -> list[tuple[str, str]]:
    """Return a list of ``(cell_type, source)`` tuples for every cell.

    Only ``cell_type`` and ``source`` are considered; outputs, execution
    counts, and cell metadata are ignored.
    """
    return [
        (cell.get("cell_type", ""), _normalise_source(cell.get("source", "")))
        for cell in notebook.get("cells", [])
    ]


def sources_match(local_nb: dict[str, Any], remote_nb: dict[str, Any]) -> bool:
    """Return ``True`` when both notebooks have identical cell sources."""
    return get_cell_sources(local_nb) == get_cell_sources(remote_nb)


# ---------------------------------------------------------------------------
# Sphinx event handler
# ---------------------------------------------------------------------------


def _process_notebooks(app: Sphinx) -> None:
    """Sphinx ``builder-inited`` handler.

    Scans *app.srcdir* recursively for ``.ipynb`` files that declare a
    ``sphinxnotebookgist.url`` in their top-level metadata.  For each such
    notebook the executed version is fetched, sources are compared, and – if
    they match – the local file is replaced with the executed notebook.
    """
    srcdir = Path(app.srcdir)

    for nb_path in sorted(srcdir.rglob("*.ipynb")):
        # Skip Jupyter checkpoint files
        if ".ipynb_checkpoints" in nb_path.parts:
            continue

        try:
            with nb_path.open(encoding="utf-8") as fh:
                local_nb: dict[str, Any] = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise ExtensionError(
                f"sphinxnotebookgist: could not read {nb_path}: {exc}"
            ) from exc

        nb_meta = local_nb.get("metadata", {})
        plugin_meta = nb_meta.get("sphinxnotebookgist")
        if not isinstance(plugin_meta, dict):
            continue

        url: str | None = plugin_meta.get("url")
        if not url:
            continue

        # Emit a status line visible with sphinx -v
        try:
            app.info(  # type: ignore[attr-defined]
                f"sphinxnotebookgist: processing {nb_path.name} from {url}"
            )
        except AttributeError:
            pass  # older Sphinx versions

        raw_url = resolve_url(url)
        executed_nb = fetch_notebook(raw_url)

        if not sources_match(local_nb, executed_nb):
            raise ExtensionError(
                f"sphinxnotebookgist: notebook {nb_path} differs from the "
                f"executed version at {url!r}.\n"
                "The source cells do not match. Please update the source "
                "notebook to match the executed version, or re-execute and "
                "re-publish the notebook."
            )

        # Sources match – replace the local file with the executed notebook
        try:
            with nb_path.open("w", encoding="utf-8") as fh:
                json.dump(executed_nb, fh, indent=1, ensure_ascii=False)
                fh.write("\n")
        except OSError as exc:
            raise ExtensionError(
                f"sphinxnotebookgist: could not write {nb_path}: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Sphinx extension entry point
# ---------------------------------------------------------------------------


def setup(app: Sphinx) -> dict[str, Any]:
    """Register the extension with Sphinx."""
    app.connect("builder-inited", _process_notebooks)
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
