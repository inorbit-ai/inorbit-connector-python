#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
from unittest import mock

# Third-party
import pytest
import yaml

# InOrbit
from inorbit_connector import utils
from inorbit_connector.logging.logger import LogLevels


class TestLogLevels:
    def test_values(self):
        assert LogLevels.DEBUG == "DEBUG"
        assert LogLevels.INFO == "INFO"
        assert LogLevels.WARNING == "WARNING"
        assert LogLevels.ERROR == "ERROR"
        assert LogLevels.CRITICAL == "CRITICAL"

    def test_isinstance(self):
        assert isinstance(LogLevels.DEBUG, str)
        assert isinstance(LogLevels.INFO, str)
        assert isinstance(LogLevels.WARNING, str)
        assert isinstance(LogLevels.ERROR, str)
        assert isinstance(LogLevels.CRITICAL, str)


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="id1: {k1: v1, k2: v2}\nid2: {k3: v3, k4: v4}",
)
def test_read_yaml_returns_entire_file(_):
    result = utils.read_yaml("dummy.yaml")
    expected = {"id1": {"k1": "v1", "k2": "v2"}, "id2": {"k3": "v3", "k4": "v4"}}
    assert result == expected


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="id1: {k1: v1, k2: v2}\nid2: {k3: v3, k4: v4}",
)
def test_read_yaml_returns_specific_robot(_):
    result = utils.read_yaml("dummy.yaml", "id1")
    expected = {"k1": "v1", "k2": "v2"}
    assert result == expected


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="id1: {k1: v1, k2: v2}\nid2: {k3: v3, k4: v4}",
)
def test_read_yaml_raises_error_when_robot_id_not_present(_):
    with pytest.raises(IndexError):
        utils.read_yaml("dummy.yaml", "id3")


@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="")
def test_read_yaml_returns_empty_dict_when_file_empty(_):
    result = utils.read_yaml("dummy.yaml")
    expected = {}
    assert result == expected


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="not: yaml: file: invalid: content",
)
def test_read_yaml_raises_error_when_invalid_yaml(_):
    with pytest.raises(yaml.YAMLError):
        utils.read_yaml("dummy.yaml")


def test_read_yaml_raises_error_when_file_not_found():
    with pytest.raises(FileNotFoundError):
        utils.read_yaml("not_found.yaml")
