---
title: "Commands Handling"
description: "How to handle commands from InOrbit"
---

Commands from InOrbit are automatically routed to your `_inorbit_robot_command_handler()` method in the case of a fleet connector, or to your `_inorbit_command_handler()` method in the case of a single-robot connector.

The fleet handler `_inorbit_robot_command_handler()` receives the following parameters:
- `robot_id` (str): The ID of the robot receiving the command
- `command_name` (str): The name of the command
- `args` (list): Command arguments
- `options` (dict): Options including `result_function` to report results

While the single-robot handler `_inorbit_command_handler()` omits the `robot_id` parameter.

```python
@override
async def _inorbit_robot_command_handler(
    self, robot_id: str, command_name: str, args: list, options: dict
) -> None:
    """Handle InOrbit commands for a specific robot."""
    if command_name == "start_mission":
        result = await self._fleet_manager.send_command(
            robot_id, "start_mission", args[0]
        )
```

A more complete example including all provided utilities is available [at the bottom](#example-usage) of this page.

## Reporting Command Results

The `options` dictionary contains a `result_function` with the following signature:
```python
options['result_function'](
    result_code: CommandResultCode,
    execution_status_details: str | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
) -> None
```
- The `result_code` parameter must be set to `CommandResultCode.SUCCESS` or `CommandResultCode.FAILURE` to report the command result.
- The `execution_status_details` and `stderr` parameters are optional and can be used to provide specific error details.
- The `stdout` parameter is optional and can be used to provide specific output details.

### Reporting Success

The commands handler can call the `result_function` with a `CommandResultCode.SUCCESS` to report a successful command execution before returning. The `stdout` parameter is optional and can be used to provide specific output details.

```python
options["result_function"](
    CommandResultCode.SUCCESS,
    stdout="Mission dispatched with ID 123456",
)
```

(reporting-failure)=
### Reporting Failure

There are three ways to report a failed command execution:

1. (Recommended) Raise a `CommandFailure` exception.
2. Raise any other exception.
3. Call the `result_function` with a `CommandResultCode.FAILURE` and provide the `execution_status_details` and `stderr` parameters.

Unhandled exceptions raised during the execution of the command handler will be caught and reported with a generic error message in its execution details, and the exception message attached to the `stderr` field. All exceptions are logged.

The `CommandFailure` exception can be used to intentionally indicate a failure:
- Error details are automatically passed to InOrbit's result function
- `execution_status_details` is displayed in alert messages when commands are dispatched from the actions UI
- Both `execution_status_details` and `stderr` are available in audit logs and through the [action execution details API](https://api.inorbit.ai/docs/index.html#operation/getActionExecutionStatus)

Example usage:

```python
from inorbit_connector.connector import CommandResultCode, CommandFailure

@override
async def _inorbit_robot_command_handler(
    self, robot_id: str, command_name: str, args: list, options: dict
) -> None:
    """Handle InOrbit commands for a specific robot."""
    if command_name == "start_mission":
        try:
            if robot_id not in self.robot_ids:
                raise CommandFailure(
                    execution_status_details=f"Robot {robot_id} not found in fleet",
                    stderr="Invalid robot ID"
                )

            result = await self._fleet_manager.send_command(
                robot_id, "start_mission", args[0]
            )
            if not result:
                raise CommandFailure(
                    execution_status_details=f"Failed to start mission for {robot_id}",
                    stderr="Fleet manager returned error"
                )
            options["result_function"](CommandResultCode.SUCCESS)
        except ValueError as e:
            raise CommandFailure(
                execution_status_details=f"Invalid parameters for {robot_id}",
                stderr=str(e)
            )
```

## Parsing Script Arguments

When handling custom script commands, the Edge SDK delivers arguments in the form:

- `args[0]`: script file name (e.g., `"script.sh"`)
- `args[1]`: a flat list of alternating keys and values (e.g., `["x", "1.0", "y", "2.0"]`)

In the case of InOrbit actions of `RunScript` type (identified with the `command_name` `COMMAND_CUSTOM_COMMAND`),
the script name corresponds to the `filename` field of the action definition,
and the arguments key-value pairs.

For details on how to configure actions with arguments, refer to the
[InOrbit Actions Definitions documentation](https://developer.inorbit.ai/docs#configuring-action-definitions).

Use the helper `parse_custom_command_args()` to turn these into a script name and a parameters dictionary:

```python
from inorbit_connector.connector import (
    parse_custom_command_args,
    CommandResultCode,
    CommandFailure,
)
from inorbit_edge.commands import COMMAND_CUSTOM_COMMAND

@override
async def _inorbit_robot_command_handler(
    self, robot_id: str, command_name: str, args: list, options: dict
) -> None:
    if command_name == COMMAND_CUSTOM_COMMAND:
        # args format: [file_name, [k1, v1, k2, v2, ...]]
        script, params = parse_custom_command_args(args)
        # Example: script == "script.sh", params == {"x": "1.0", "y": "2.0"}
        # Use script and params as needed
        options["result_function"](
            CommandResultCode.SUCCESS,
            stdout=f"Ran {script} with params {params}",
        )
```

It is recommended to complement its use with the `CommandModel` class (see [Using CommandModel for Type-Safe Argument Parsing](#using-commandmodel-for-type-safe-argument-parsing)) for safe type validation and parsing.

(using-commandmodel-for-type-safe-argument-parsing)=
## Using `CommandModel` for Type-Safe Argument Parsing

For structured command arguments that require validation and type safety, use the `CommandModel` base class. This is particularly useful when commands have multiple parameters with specific types and validation rules.

`CommandModel` provides:
- Automatic type validation and conversion using Pydantic
- Conversion of validation errors to [`CommandFailure`](#reporting-failure) exceptions
- Protection against extra fields (forbids unknown parameters)

Optionally, you can combine `CommandModel` with `ExcludeUnsetMixin` to exclude unset fields from model dumps, which is useful for API calls where you only want to send non-default values.

### Basic Usage

Define a command model by subclassing `CommandModel`:

```python
from inorbit_connector.commands import CommandModel, parse_custom_command_args
from inorbit_connector.connector import CommandResultCode, CommandFailure

class CommandQueueMission(CommandModel):
    """Command model for queue_mission command."""
    mission_id: str
    robot_id: int | None = None
    priority: int | None = None
    description: str | None = None
```

### Using with `ExcludeUnsetMixin`

To exclude unset fields from model dumps (useful for API calls), inherit from both `ExcludeUnsetMixin` and `CommandModel`. The mixin must come first in the inheritance list:

```python
from inorbit_connector.commands import CommandModel, ExcludeUnsetMixin

class CommandQueueMission(ExcludeUnsetMixin, CommandModel):
    """Command model for queue_mission command."""
    mission_id: str
    robot_id: int | None = None
    priority: int | None = None
    description: str | None = None
```

### Using with `parse_custom_command_args`

`CommandModel` works seamlessly with `parse_custom_command_args()`:

```python
from inorbit_edge.commands import COMMAND_CUSTOM_COMMAND

@override
async def _inorbit_robot_command_handler(
    self, robot_id: str, command_name: str, args: list, options: dict
) -> None:
    if command_name == COMMAND_CUSTOM_COMMAND:
        script_name, script_args = parse_custom_command_args(args)

        if script_name == "queue_mission":
            # Validation happens automatically - raises CommandFailure on error
            command = CommandQueueMission(**script_args)

            # If using ExcludeUnsetMixin, model_dump() excludes unset fields
            # Useful for API calls where you only want to send non-default values
            await self._fleet_client.schedule_mission(**command.model_dump())

            options["result_function"](CommandResultCode.SUCCESS)
```

### Automatic Error Handling

If validation fails, `CommandModel` automatically raises a `CommandFailure` with appropriate error details:

```python
# If script_args contains invalid data:
# script_args = {"mission_id": "test", "priority": "not_an_int"}
command = CommandQueueMission(**script_args)
# Raises CommandFailure with execution_status_details="Bad arguments"
# and stderr containing the validation error details
```

The exception is automatically handled by the connector's command execution framework, so you don't need to catch `ValidationError` exceptions.
See the [Reporting Failure](#reporting-failure) section for more details.

### Excluding Unset Fields

When using `ExcludeUnsetMixin`, `model_dump()` excludes fields that weren't explicitly set, which is useful when making API calls where you only want to send non-default values:

```python
# With ExcludeUnsetMixin
command = CommandQueueMission(mission_id="test123", priority=5)
command.model_dump()
# Returns: {"mission_id": "test123", "priority": 5}
# Note: robot_id and description are excluded since they weren't set

# Without ExcludeUnsetMixin
class SimpleCommand(CommandModel):
    mission_id: str
    priority: int | None = None

command = SimpleCommand(mission_id="test123")
command.model_dump()
# Returns: {"mission_id": "test123", "priority": None}
# All fields are included, even if they have default values
```

(example-usage)=
## Example Usage

Here's a concrete example of using `CommandModel` with `ExcludeUnsetMixin` to handle a custom command.

The command is a RunScript action, whose filename is `schedule_mission`.

```yaml
# ActionDefinition.yaml
apiVersion: v0.1
kind: ActionDefinition
metadata:
  id: dock
  scope: tag/my-account-id/my-collection-id # Or any applicable scope
spec:
  type: RunScript
  arguments:
  - name: filename
    type: string
    value: schedule_mission
  - name: mission_id
    type: string
    value: 4eaa3a62-7a17-11ed-9f3c-0001299981c4
  description: Sends robot to charging dock
  label: Dock
```

Once applied using the [InOrbit CLI](https://developer.inorbit.ai/docs#using-the-inorbit-cli) or [REST APIs](https://api.inorbit.ai/docs/index.html#tag/configAPI), the action can be executed through the InOrbit UI or through the [REST APIs](https://api.inorbit.ai/docs/index.html#tag/actions).

```shell
# Apply the action definition
inorbit apply -f ActionDefinition.yaml

# Execute the action
curl --location 'https://api.inorbit.ai/robots/<robot-id>/actions' \
--header 'Content-Type: application/json' \
--header 'Accept: application/json' \
--header 'x-auth-inorbit-app-key: <app-key>' \
--data '
{
    "actionId": "dock"
}'
```

The connector implements the command handler for the `schedule_mission` command and passes the arguments to an API client to schedule the mission.

```python
from enum import StrEnum
from inorbit_connector.commands import CommandModel, ExcludeUnsetMixin, parse_custom_command_args
from inorbit_connector.connector import CommandResultCode
from inorbit_edge.commands import COMMAND_CUSTOM_COMMAND

class CommandScheduleMission(ExcludeUnsetMixin, CommandModel):
    """Command model for scheduling a mission."""
    mission_id: str
    robot_id: int | None = None
    priority: int | None = None

class CustomScripts(StrEnum):
    """Custom scripts supported by the connector."""
    SCHEDULE_MISSION = "schedule_mission"
    # Add other custom scripts here

class ExampleConnector(Connector):
    ... # other methods

    @override
    async def _inorbit_command_handler(
        self, command_name: str, args: list, options: dict
    ) -> None:
        if command_name == COMMAND_CUSTOM_COMMAND:
            script_name, script_args = parse_custom_command_args(args)
            # script_name = "schedule_mission"
            # script_args = {"mission_id": "4eaa3a62-7a17-11ed-9f3c-0001299981c4"}

            if script_name == CustomScripts.SCHEDULE_MISSION:
                # Validation and type conversion happen automatically
                command = CommandScheduleMission(**script_args)

                # Only explicitly set fields are included in the dump
                await self._api_client.schedule_mission(**command.model_dump())

            else:
                raise CommandFailure(
                    execution_status_details=f"Command not implemented",
                    stderr=f"Command '{script_name}' not yet implemented",
                )

            # Call the result function to indicate success
            options["result_function"](CommandResultCode.SUCCESS)
        else:
            raise CommandFailure(
                execution_status_details=f"Command not implemented",
                stderr=f"Command '{command_name}' not yet implemented",
            )
```
