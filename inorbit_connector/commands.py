#!/usr/bin/env python

# Copyright 2025 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
from enum import Enum

# Python 3.12+ compatibility for override decorator
try:
    from typing import Any, override
except ImportError:
    from typing import Any
    from typing_extensions import override

# Third Party
from pydantic import BaseModel, ConfigDict, ValidationError

"""Command handling utilities for InOrbit connectors.

This module provides classes and functions for handling commands in InOrbit connectors,
including argument parsing, validation, and error handling.
"""


class CommandResultCode(str, Enum):
    """The result code of a command execution."""

    SUCCESS = "0"
    FAILURE = "1"


class CommandFailure(Exception):
    """
    Exception raised when a command fails to execute.

    Its data will be passed to the result function and result_code will be set to
    FAILURE if the exception is raised during the execution of a custom command
    registered by a connector.

    Both values will be displayed in the audit logs and will be available through the
    action execution details API endpoint. See
        https://api.inorbit.ai/docs/index.html#operation/getActionExecutionStatus

    If the command is dispatched from the actions UI, execution_status_details will be
    displayed in the alert message upon command execution failure.
    """

    def __init__(self, execution_status_details: str, stderr: str):
        super().__init__(execution_status_details)
        self.execution_status_details = execution_status_details
        self.stderr = stderr


def parse_custom_command_args(custom_command_args) -> tuple[str, dict[str, Any]]:
    """Parse custom command arguments of a COMMAND_CUSTOM_COMMAND command from the
    edge-sdk.

    Assumes custom_command_args corresponds to a COMMAND_CUSTOM_COMMAND command from the
    edge-sdk. The first item of the list corresponds to the script name, and the second
    is a list of arguments.
    In the case of InOrbit actions of RunScript type, the script name corresponds to the
    filename, and the arguments are pairs of named arguments.
    Refer to the InOrbit Actions documentation for details on how to configure actions:
     - https://developer.inorbit.ai/docs#configuring-action-definitions

    Outputs the script name and a dictionary with argument-value pairs. e.g.:
        ("script.sh", {"x": "1.0", "y": "2.0"})

    Args:
        custom_command_args: List-like container with the custom command arguments.

    Returns:
        Tuple with the script name and a dictionary with argument-value pairs.

    Raises:
        ValueError: If the arguments are not compliant with edge-sdk types. If this
            function is used correctly, this should never happen.
        CommandFailure: If the arguments cannot be parsed as key-value pairs.
            Note: This exception should not be handled by the commands handler.
            See CommandFailure for more details.
    """
    if not isinstance(custom_command_args, list):
        raise ValueError(
            "Expected custom command arguments to be a list, "
            f"got {type(custom_command_args)}"
        )

    if len(custom_command_args) != 2:
        raise ValueError(
            "Expected custom command arguments to be a list with two elements."
        )

    script_name = custom_command_args[0]
    args_list_raw = custom_command_args[1]

    if not isinstance(script_name, str):
        raise ValueError("Script name must be a string")

    # Convert any iterable container into a list for processing and verify the result
    # Exclude strings and bytes, which are iterables that can be converted to lists
    if isinstance(args_list_raw, (str, bytes)):
        raise ValueError("Arguments must be a list-like container")
    try:
        args_list = list(args_list_raw)
    except TypeError:
        raise ValueError("Arguments must be a list-like container")

    if len(args_list) % 2 != 0:
        raise CommandFailure(
            execution_status_details="Invalid script arguments provided",
            stderr=(
                "The script arguments must be a list of key-value pairs, "
                f"got {len(args_list)} elements"
            ),
        )

    # Last value wins on duplicate keys; preserve original types
    params = {k: v for k, v in zip(args_list[::2], args_list[1::2])}
    return script_name, params


class ExcludeUnsetMixin:
    """Mixin class that excludes unset fields from model dumps by default.

    This mixin overrides the model_dump() method to set exclude_unset=True by
    default, which is useful when you only want to serialize fields that were
    explicitly set. This is particularly useful for API calls where you only want
    to send non-default values.

    Example:
        class MyModel(ExcludeUnsetMixin, BaseModel):
            field1: str
            field2: int | None = None

        model = MyModel(field1="value")
        model.model_dump()  # Returns {"field1": "value"} (field2 excluded)
        model.model_dump(exclude_unset=False)
        # Returns {"field1": "value", "field2": None}
    """

    @override  # type: ignore[override]
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Dump the model to a dictionary.

        Excludes unset fields by default.
        """
        kwargs.setdefault("exclude_unset", True)
        return super().model_dump(*args, **kwargs)


class CommandModel(BaseModel):
    """Base class for parsing and validating command arguments.

    This class provides a convenient way to parse and validate command arguments
    using Pydantic models. It automatically converts ValidationError exceptions
    to CommandFailure exceptions, which are properly handled by the connector's
    command execution framework.

    Features:
    - Converts ValidationError into CommandFailure for proper error handling
    - Forbids extra fields by default (extra="forbid")

    To exclude unset fields from model dumps, inherit from both CommandModel
    and ExcludeUnsetMixin:

        class CommandQueueMission(ExcludeUnsetMixin, CommandModel):
            mission_id: str
            robot_id: int | None = None
            priority: int | None = None

    Pydantic models automatically cast values to the correct type whenever possible.

    Example:
        class CommandQueueMission(ExcludeUnsetMixin, CommandModel):
            mission_id: str
            robot_id: int | None = None
            priority: int | None = None

        # In command handler:
        script_name, script_args = parse_custom_command_args(args)
        command = CommandQueueMission(**script_args)
        # If validation fails, CommandFailure is raised automatically
        # model_dump() excludes unset fields when using ExcludeUnsetMixin
        await api_client.schedule_mission(**command.model_dump())
    """

    model_config = ConfigDict(extra="forbid")

    def __init__(self, **data: Any):
        try:
            super().__init__(**data)
        except ValidationError as e:
            raise CommandFailure(
                execution_status_details="Bad arguments", stderr=str(e)
            ) from e

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        try:
            return super().model_validate(obj, *args, **kwargs)
        except ValidationError as e:
            raise CommandFailure(
                execution_status_details="Bad arguments", stderr=str(e)
            ) from e

    @classmethod
    def model_validate_json(cls, json_data: str, *args, **kwargs):
        try:
            return super().model_validate_json(json_data, *args, **kwargs)
        except ValidationError as e:
            raise CommandFailure(
                execution_status_details="Bad arguments", stderr=str(e)
            ) from e
