#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

"""The setup script."""

from setuptools import find_packages, setup

VERSION = "0.4.1"

GITHUB_ORG_URL = "https://github.com/inorbit-ai"
GITHUB_REPO_URL = f"{GITHUB_ORG_URL}/inorbit-connector-python"

with open("README.md") as file:
    long_description = file.read()

with open("requirements.txt", "r") as file:
    install_requirements = file.read().splitlines()

setup(
    author="InOrbit, Inc.",
    author_email="support@inorbit.ai",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    description="A Python library for connectors in the InOrbit RobOps ecosystem.",
    download_url=f"{GITHUB_REPO_URL}/archive/refs/tags/{VERSION}.zip",
    install_requires=install_requirements,
    keywords=["inorbit", "robops", "robotics"],
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    maintainer="Russell Toris",
    maintainer_email="russell@inorbit.ai",
    name="inorbit-connector",
    packages=find_packages(),
    platforms=["Linux", "Windows", "macOS"],
    project_urls={
        "Tracker": f"{GITHUB_REPO_URL}/issues",
        "Contributing": f"{GITHUB_REPO_URL}/blob/v{VERSION}/CONTRIBUTING.md",
        "Code of Conduct": f"{GITHUB_REPO_URL}/blob/v{VERSION}/CODE_OF_CONDUCT.md",
        "Changelog": f"{GITHUB_REPO_URL}/blob/v{VERSION}/CHANGELOG.md",
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
    python_requires=">=3.10, <3.13",
    url=GITHUB_REPO_URL,
    version=VERSION,
)
