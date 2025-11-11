<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Commands Handling

Commands from InOrbit are automatically routed to your `_inorbit_robot_command_handler()` method in the case of a fleet connector, or to your `_inorbit_command_handler()` method in the case of a single-robot connector.

The fleet handler `_inorbit_robot_command_handler()` receives the following parameters:
- `robot_id` (str): The ID of the robot receiving the command
- `command_name` (str): The name of the command
- `args` (list): Command arguments
- `options` (dict): Options including `result_function` to report results

While the single-robot handler `_inorbit_command_handler()` omits the `robot_id` parameter.

## Example Usage

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
