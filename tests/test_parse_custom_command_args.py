#!/usr/bin/env python

# Copyright 2025 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

import pytest


from inorbit_connector.connector import (
    parse_custom_command_args,
    CommandFailure,
)
from inorbit_edge.inorbit_pb2 import CustomScriptCommandMessage


def test_parse_custom_command_args_happy_path():
    script, params = parse_custom_command_args(
        ["script.sh", ["x", "1.0", "y", "2.0"]]
    )
    assert script == "script.sh"
    assert params == {"x": "1.0", "y": "2.0"}


def test_parse_custom_command_args_empty_params():
    script, params = parse_custom_command_args(["script.sh", []])
    assert script == "script.sh"
    assert params == {}


def test_parse_custom_command_args_odd_length_raises_command_failure():
    with pytest.raises(CommandFailure) as exc:
        parse_custom_command_args(["script.sh", ["x", "1.0", "y"]])
    assert "Invalid script arguments provided" in str(exc.value)


def test_parse_custom_command_args_top_level_not_list_raises_value_error():
    with pytest.raises(ValueError):
        parse_custom_command_args("not a list")


def test_parse_custom_command_args_wrong_length_raises_value_error():
    with pytest.raises(ValueError):
        parse_custom_command_args(["script.sh", ["k", "v"], "extra"])


def test_parse_custom_command_args_args_not_list_raises_value_error():
    with pytest.raises(ValueError):
        parse_custom_command_args(["script.sh", "k=v"])


def test_parse_custom_command_args_script_name_not_str_raises_value_error():
    with pytest.raises(ValueError):
        parse_custom_command_args([123, ["x", "1"]])


def test_parse_custom_command_args_duplicate_keys_last_wins_and_type_preserved():
    script, params = parse_custom_command_args(
        ["script.sh", ["x", 1, "x", True, "y", 3.14]]
    )
    assert script == "script.sh"
    # Last write wins for 'x'; values/types preserved
    assert params == {"x": True, "y": 3.14}


def test_parse_custom_command_args_accepts_iterable_like_tuple_or_container():
    # Use a tuple to simulate a non-list iterable (e.g., protobuf repeated field)
    iterable_args = ("a", 1, "b", 2)
    script, params = parse_custom_command_args(["script.sh", iterable_args])
    assert script == "script.sh"
    assert params == {"a": 1, "b": 2}


def test_parse_custom_command_args_accepts_protobuf_repeated_field():
    msg = CustomScriptCommandMessage()
    msg.file_name = "script.sh"
    msg.arg_options.extend(["x", "1.0", "y", "2.0"])

    script, params = parse_custom_command_args([msg.file_name, msg.arg_options])
    assert script == "script.sh"
    assert params == {"x": "1.0", "y": "2.0"}


def test_parse_custom_command_args_protobuf_repeated_odd_length_raises():
    msg = CustomScriptCommandMessage()
    msg.file_name = "script.sh"
    msg.arg_options.extend(["x", "1.0", "y"])  # odd number of elements

    with pytest.raises(CommandFailure):
        parse_custom_command_args([msg.file_name, msg.arg_options])


