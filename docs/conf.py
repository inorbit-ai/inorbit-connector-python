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
import sys

# Ensure the package can be imported so we can read its version
sys.path.insert(0, os.path.abspath(".."))

project = 'inorbit-connector'
copyright = '2025, InOrbit, Inc.'
author = 'InOrbit, Inc.'

from inorbit_connector import __version__
release = __version__
version = __version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'myst_parser',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']

# Support both Markdown (MyST) and reStructuredText sources
source_suffix = {
    '.md': 'markdown',
    '.rst': 'restructuredtext',
}

# Brand the Furo theme
html_theme_options = {
    "light_logo": "inorbit-logo-black.svg",
    "dark_logo": "inorbit-logo-white.svg",
}
