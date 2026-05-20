#!/usr/bin/env python

# Copyright 2024 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import os

# Third-party
import yaml

# Constants
DEFAULT_TIMEZONE = "UTC"
DEFAULT_LOGGING_CONFIG = os.path.join(
    os.path.dirname(__file__), "logging/logging.default.conf"
)


def read_yaml(fname: str) -> dict:
    """Reads a YAML file and returns the data as a dictionary.

    Args:
        fname (str): The file name or path of the YAML file

    Returns:
        dict: The data read from the YAML file as a dictionary
    Raises:
        FileNotFoundError: If the configuration file does not exist
        yaml.YAMLError: If the configuration file is not valid YAML
    """
    with open(fname, "r") as file:
        data = yaml.safe_load(file)
        return data if data is not None else {}
