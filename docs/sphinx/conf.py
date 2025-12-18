# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import re
from pathlib import Path


def _read_package_version() -> str:
    """Read __version__ from the package without importing it.

    This keeps the docs build independent from the environment (no need to have the
    package importable).
    """
    repo_root = Path(__file__).resolve().parents[2]
    init_py = repo_root / "inorbit_connector" / "__init__.py"
    text = init_py.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not determine package version from __init__.py")
    return match.group(1)


project = "inorbit-connector"
copyright = "2025, InOrbit, Inc."
author = "InOrbit, Inc."

release = _read_package_version()
version = release

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
]

myst_enable_extensions = [
    "colon_fence",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

root_doc = "index"

# The portable docs use explicit HTML anchors (e.g. <a id="..."></a>) for deep
# linking compatibility across doc systems. MyST can't validate those anchors,
# and will emit "xref_missing" warnings for links that include a fragment.
suppress_warnings = ["myst.xref_missing"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["../contents/_static"]

# Support both Markdown (MyST) and reStructuredText sources
source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}


def _read_static_svg(filename: str) -> str:
    static_dir = Path(__file__).resolve().parents[1] / "contents" / "_static"
    return (static_dir / filename).read_text(encoding="utf-8")


# Brand the Furo theme
html_theme_options = {
    "light_logo": "inorbit-logo-black.svg",
    "dark_logo": "inorbit-logo-white.svg",
    "source_repository": "https://github.com/inorbit-ai/inorbit-connector-python/",
    "source_branch": "main",
    "source_directory": "docs/contents/",
    "top_of_page_buttons": ["view", "edit"],
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/inorbit-ai/inorbit-connector-python",
            "html": _read_static_svg("mark-github.svg"),
            "class": "",
        }
    ],
}

# Favicon
html_favicon = "../contents/_static/favicon.ico"
