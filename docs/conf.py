# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
import os
from pathlib import Path
import sys

from inorbit_connector import __version__

# Ensure the package can be imported so we can read its version
sys.path.insert(0, os.path.abspath(".."))

project = "inorbit-connector"
copyright = "2025, InOrbit, Inc."
author = "InOrbit, Inc."

release = __version__
version = __version__

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

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]

# Support both Markdown (MyST) and reStructuredText sources
source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}


def _read_static_svg(filename: str) -> str:
    static_dir = Path(__file__).resolve().parent / "_static"
    return (static_dir / filename).read_text(encoding="utf-8")


# Brand the Furo theme
html_theme_options = {
    "light_logo": "inorbit-logo-black.svg",
    "dark_logo": "inorbit-logo-white.svg",
    "source_repository": "https://github.com/inorbit-ai/inorbit-connector-python/",
    "source_branch": "main",
    "source_directory": "docs/",
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
html_favicon = "_static/favicon.ico"
