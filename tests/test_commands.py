#!/usr/bin/env python

# Copyright 2025 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

import pytest
from pydantic import BaseModel, ValidationError
from inorbit_edge.inorbit_pb2 import CustomScriptCommandMessage

from inorbit_connector.commands import (
    CommandFailure,
    CommandModel,
    ExcludeUnsetMixin,
    parse_custom_command_args,
)
from inorbit_connector.connector import (
    CommandFailure as ConnectorCommandFailure,
    parse_custom_command_args as connector_parse_custom_command_args,
)


# Test models for ExcludeUnsetMixin
class ModelWithMixin(ExcludeUnsetMixin, BaseModel):
    """Test model using ExcludeUnsetMixin."""

    field1: str
    field2: int | None = None
    field3: str = "default"


# Test models for CommandModel
class SimpleCommand(ExcludeUnsetMixin, CommandModel):
    """Simple command model for testing."""

    command_id: str
    priority: int | None = None
    description: str | None = None


class CommandWithRequiredFields(CommandModel):
    """Command model with all required fields (without mixin)."""

    mission_id: str
    robot_id: int


class CommandWithoutMixin(CommandModel):
    """Command model without ExcludeUnsetMixin for testing."""

    command_id: str
    priority: int | None = None
    description: str | None = None


# ==============================================================================
# Tests for ExcludeUnsetMixin
# ==============================================================================


def test_exclude_unset_mixin_excludes_unset_fields_by_default():
    """Test that ExcludeUnsetMixin excludes unset fields by default."""
    model = ModelWithMixin(field1="value1")
    result = model.model_dump()
    assert result == {"field1": "value1"}
    assert "field2" not in result
    assert "field3" not in result


def test_exclude_unset_mixin_can_override_exclude_unset():
    """Test that exclude_unset=False can override the default."""
    model = ModelWithMixin(field1="value1", field2=42)
    result = model.model_dump(exclude_unset=False)
    assert result == {"field1": "value1", "field2": 42, "field3": "default"}


def test_exclude_unset_mixin_includes_set_fields():
    """Test that set fields are included even if they match defaults."""
    model = ModelWithMixin(field1="value1", field3="custom")
    result = model.model_dump()
    assert result == {"field1": "value1", "field3": "custom"}
    assert "field2" not in result


# ==============================================================================
# Tests for CommandModel
# ==============================================================================


def test_command_model_forbids_extra_fields():
    """Test that CommandModel forbids extra fields."""
    with pytest.raises(CommandFailure) as exc_info:
        SimpleCommand(command_id="test", extra_field="not allowed")
    assert "Bad arguments" in str(exc_info.value.execution_status_details)
    assert isinstance(exc_info.value, CommandFailure)


def test_command_model_validation_error_converted_to_command_failure_in_init():
    """Test that ValidationError in __init__ is converted to CommandFailure."""
    with pytest.raises(CommandFailure) as exc_info:
        SimpleCommand(command_id="test", priority="not_an_int")
    assert "Bad arguments" in str(exc_info.value.execution_status_details)
    assert isinstance(exc_info.value, CommandFailure)


def test_command_model_validation_error_converted_to_command_failure_in_validate():
    """Test that ValidationError in model_validate is converted to CommandFailure."""
    with pytest.raises(CommandFailure):
        SimpleCommand.model_validate({"command_id": "test", "priority": "not_an_int"})


def test_command_model_validation_error_converted_to_command_failure_in_validate_json():
    """Test that ValidationError in model_validate_json is converted to CommandFailure."""
    with pytest.raises(CommandFailure):
        SimpleCommand.model_validate_json(
            '{"command_id": "test", "priority": "not_an_int"}'
        )


def test_command_model_excludes_unset_fields():
    """Test that CommandModel with ExcludeUnsetMixin excludes unset fields."""
    command = SimpleCommand(command_id="test123")
    result = command.model_dump()
    assert result == {"command_id": "test123"}
    assert "priority" not in result
    assert "description" not in result


def test_command_model_without_mixin_includes_all_fields():
    """Test that CommandModel without ExcludeUnsetMixin includes all fields."""
    command = CommandWithoutMixin(command_id="test123")
    result = command.model_dump()
    assert result == {"command_id": "test123", "priority": None, "description": None}


def test_command_model_includes_set_fields():
    """Test that CommandModel with ExcludeUnsetMixin includes set fields."""
    command = SimpleCommand(command_id="test123", priority=5)
    result = command.model_dump()
    assert result == {"command_id": "test123", "priority": 5}
    assert "description" not in result


def test_command_model_with_all_fields_set():
    """Test CommandModel with all fields set."""
    command = SimpleCommand(
        command_id="test123", priority=10, description="Test command"
    )
    result = command.model_dump()
    assert result == {
        "command_id": "test123",
        "priority": 10,
        "description": "Test command",
    }


def test_command_model_type_casting():
    """Test that CommandModel automatically casts types when possible."""
    command = SimpleCommand.model_validate({"command_id": "test", "priority": "42"})
    assert command.priority == 42
    assert isinstance(command.priority, int)


def test_command_model_with_required_fields_only():
    """Test CommandModel with only required fields."""
    command = CommandWithRequiredFields(mission_id="mission1", robot_id=123)
    result = command.model_dump()
    assert result == {"mission_id": "mission1", "robot_id": 123}


def test_command_model_validation_preserves_original_error():
    """Test that CommandFailure preserves the original ValidationError."""
    with pytest.raises(CommandFailure) as exc_info:
        SimpleCommand(command_id="test", priority="not_an_int")
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, ValidationError)


# ==============================================================================
# Tests for parse_custom_command_args
# ==============================================================================


def test_parse_custom_command_args_happy_path():
    script, params = parse_custom_command_args(["script.sh", ["x", "1.0", "y", "2.0"]])
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


# ==============================================================================
# Tests for backwards compatibility
# TODO: Remove in the next major release
# ==============================================================================


def test_command_failure_importable_from_connector():
    """Test that CommandFailure can still be imported from connector module."""
    assert CommandFailure is ConnectorCommandFailure
    failure = CommandFailure("test", "error")
    assert isinstance(failure, ConnectorCommandFailure)


def test_parse_custom_command_args_importable_from_connector():
    """Test that parse_custom_command_args can still be imported from connector module."""
    assert parse_custom_command_args is connector_parse_custom_command_args
    script, params = parse_custom_command_args(["script.sh", ["x", "1.0"]])
    assert script == "script.sh"
    assert params == {"x": "1.0"}


def test_command_model_works_with_parse_custom_command_args():
    """Test that CommandModel works seamlessly with parse_custom_command_args."""
    script_name, script_args = parse_custom_command_args(
        ["queue_mission", ["command_id", "test123", "priority", "5"]]
    )
    command = SimpleCommand(**script_args)
    assert command.command_id == "test123"
    assert command.priority == 5
    result = command.model_dump()
    assert result == {"command_id": "test123", "priority": 5}


def test_command_model_invalid_args_from_parse_custom_command_args():
    """Test that invalid arguments from parse_custom_command_args raise CommandFailure."""
    script_name, script_args = parse_custom_command_args(
        ["queue_mission", ["command_id", "test123", "priority", "not_an_int"]]
    )
    with pytest.raises(CommandFailure):
        SimpleCommand(**script_args)
