#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
from unittest import mock

# Third-party
import pytest
import yaml

# Local
from inorbit_connector import utils


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="id1: {k1: v1, k2: v2}\nid2: {k3: v3, k4: v4}",
)
def test_read_yaml_returns_entire_file(mock_file):
    result = utils.read_yaml("dummy.yaml")
    expected = {"id1": {"k1": "v1", "k2": "v2"}, "id2": {"k3": "v3", "k4": "v4"}}
    assert result == expected


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="id1: {k1: v1, k2: v2}\nid2: {k3: v3, k4: v4}",
)
def test_read_yaml_returns_specific_robot(mock_file):
    result = utils.read_yaml("dummy.yaml", "id1")
    expected = {"k1": "v1", "k2": "v2"}
    assert result == expected


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="id1: {k1: v1, k2: v2}\nid2: {k3: v3, k4: v4}",
)
def test_read_yaml_raises_error_when_robot_id_not_present(mock_file):
    with pytest.raises(IndexError):
        utils.read_yaml("dummy.yaml", "id3")


@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="")
def test_read_yaml_returns_empty_dict_when_file_empty(mock_file):
    result = utils.read_yaml("dummy.yaml")
    expected = {}
    assert result == expected


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="not: yaml: file: invalid: content",
)
def test_read_yaml_raises_error_when_invalid_yaml(mock_file):
    with pytest.raises(yaml.YAMLError):
        utils.read_yaml("dummy.yaml")


def test_read_yaml_raises_error_when_file_not_found():
    with pytest.raises(FileNotFoundError):
        utils.read_yaml("not_found.yaml")
