#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

"""The setup script."""

import tomllib
from pathlib import Path
from setuptools import setup

GITHUB_ORG_URL = "https://github.com/inorbit-ai"
GITHUB_REPO_URL = f"{GITHUB_ORG_URL}/inorbit-connector-python"
VERSION = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"][
    "version"
]

setup(
    download_url=f"{GITHUB_REPO_URL}/archive/refs/tags/v{VERSION}.zip",
    project_urls={
        "Tracker": f"{GITHUB_REPO_URL}/issues",
        "Contributing": f"{GITHUB_REPO_URL}/blob/v{VERSION}/CONTRIBUTING.md",
        "Code of Conduct": f"{GITHUB_REPO_URL}/blob/v{VERSION}/CODE_OF_CONDUCT.md",
        "Issue Tracker": f"{GITHUB_REPO_URL}/issues",
        "License": f"{GITHUB_REPO_URL}/blob/v{VERSION}/LICENSE",
        "About": "https://www.inorbit.ai/company",
        "Contact": "https://www.inorbit.ai/contact",
        "Blog": "https://www.inorbit.ai/blog",
        "Twitter": "https://twitter.com/InOrbitAI",
        "LinkedIn": "https://www.linkedin.com/company/inorbitai",
        "GitHub": GITHUB_ORG_URL,
        "Website": "https://www.inorbit.ai/",
        "Source": f"{GITHUB_REPO_URL}/tree/v{VERSION}",
    },
)
