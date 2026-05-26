# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Shared pytest fixtures for the inorbit-connector test suite."""

import os

import pytest


@pytest.fixture(autouse=True)
def _clean_inorbit_env(monkeypatch):
    """Remove all ``INORBIT_*`` environment variables before each test."""
    for key in list(os.environ):
        if key.startswith("INORBIT_"):
            monkeypatch.delenv(key, raising=False)
