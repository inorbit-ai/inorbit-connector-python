---
title: "Fleet Connector"
description: "Guide for implementing a fleet connector"
---

Subclass `inorbit_connector.connector.FleetConnector` to manage multiple robots simultaneously.

## Constructor

```python
def __init__(self, config: ConnectorConfig, **kwargs) -> None
```

**Parameters:**
- `config` (ConnectorConfig): The connector configuration containing the fleet

**Keyword Arguments:**
- `register_user_scripts` (bool): Automatically register user scripts. Default: `False`
- `default_user_scripts_dir` (str): Default directory for user scripts. Default: `~/.inorbit_connectors/connector-{class_name}/local/`
- `create_user_scripts_dir` (bool): Create the user scripts directory if it doesn't exist. Default: `False`
- `register_custom_command_handler` (bool): Automatically register the command handler. Default: `True`

## Required Methods

Subclasses must implement the same abstract methods as single-robot connectors, with one difference:

### `_inorbit_robot_command_handler()`

:::{hint}
See the [Commands Handling](/ground-control/robot-integration/connector-framework/usage/commands-handling) chapter for more details.
:::

Handle commands for a specific robot. This method is automatically registered if `register_custom_command_handler` is True (default).

```python
from inorbit_connector.connector import CommandResultCode, CommandFailure

@override
async def _inorbit_robot_command_handler(
    self, robot_id: str, command_name: str, args: list, options: dict
) -> None:
    """Handle InOrbit commands for a specific robot."""
    if command_name == "start_mission":
        result = await self._fleet_manager.send_command(
            robot_id, "start_mission", args[0]
        )
        if result:
            options["result_function"](CommandResultCode.SUCCESS)
        else:
            raise CommandFailure(
                execution_status_details=f"Failed to start mission for {robot_id}",
                stderr="Fleet manager returned error"
            )
```

Exceptions raised in the command handler are automatically caught and reported. Use `CommandFailure` to provide specific error details that will be displayed in InOrbit's audit logs and action execution details.

## Fleet Management

### Accessing Robot IDs

Access the list of robot IDs in the fleet:

```python
for robot_id in self.robot_ids:
    # Process each robot
    pass
```

### Updating the Fleet

You can update the fleet configuration during `_connect()` by calling the `update_fleet()` method. This is useful for dynamically setting the robots list before the connector starts, for example, when provisioning robots from fleet manager data instead of hardcoded values in the config files:

```python
@override
async def _connect(self) -> None:
    """Connect to fleet manager and update fleet."""
    # Fetch robot list from fleet manager API
    robots = await self._fleet_manager.get_robots()
    
    # Update fleet configuration
    fleet_config = [
        RobotConfig(robot_id=robot.id, cameras=robot.cameras)
        for robot in robots
    ]
    self.update_fleet(fleet_config)
```

The `update_fleet()` method updates the fleet configuration and initializes sessions for all robots.

## Publishing Methods

All publishing methods require a `robot_id` parameter. See the [Publishing Guide](/ground-control/robot-integration/connector-framework/publishing) for detailed information.

- `publish_robot_pose(robot_id, x, y, yaw, frame_id)`: Publish pose for a specific robot
- `publish_robot_odometry(robot_id, **kwargs)`: Publish odometry for a specific robot
- `publish_robot_key_values(robot_id, **kwargs)`: Publish key-values for a specific robot
- `publish_robot_system_stats(robot_id, **kwargs)`: Publish system stats for a specific robot
- `publish_robot_map(robot_id, frame_id, is_update=False)`: Publish map for a specific robot

## Advanced Methods

### `_get_robot_session()`

Access the underlying `RobotSession` from the InOrbit Edge SDK for a specific robot. Use this for advanced use cases not covered by the connector API.

```python
def _get_robot_session(self, robot_id: str) -> RobotSession:
    """Get a robot session for a specific robot ID.
    
    Args:
        robot_id (str): The robot ID to get the session for
        
    Returns:
        RobotSession: The robot session for the specified robot
    """
```

**Example:**
```python
async def _execution_loop(self) -> None:
    for robot_id in self.robot_ids:
        # Access the session directly for advanced features
        session = self._get_robot_session(robot_id)
        # Use Edge SDK methods directly
        ...
```

## Robot Online Status

Override `_is_fleet_robot_online()` to provide custom online status checks:

```python
@override
def _is_fleet_robot_online(self, robot_id: str) -> bool:
    """Check if a robot is online."""
    # Check robot status via fleet manager API
    return self._fleet_manager.is_robot_online(robot_id)
```

This is used by InOrbit to determine robot availability.

## Example Execution Loop

```python
@override
async def _execution_loop(self) -> None:
    """Main execution loop for fleet."""
    for robot_id in self.robot_ids:
        try:
            # Fetch robot data from fleet manager
            robot_data = await self._fleet_manager.get_robot_data(robot_id)
            
            # Publish pose
            self.publish_robot_pose(
                robot_id,
                robot_data.x,
                robot_data.y,
                robot_data.yaw,
                robot_data.frame_id
            )
            
            # Publish telemetry
            self.publish_robot_key_values(robot_id, **robot_data.telemetry)
        except Exception as e:
            self._logger.error(f"Error processing robot {robot_id}: {e}")
```

## Lifecycle

The lifecycle methods are the same as single-robot connectors:
- `start()`: Start the connector
- `join()`: Block until stopped
- `stop()`: Stop the connector

## Examples

- **Simple fleet connector**: [examples/simple-fleet-connector/connector.py](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/simple-fleet-connector/connector.py)
- **Fleet connector (CLI)**: [examples/fleet-connector/](https://github.com/inorbit-ai/inorbit-connector-python/tree/main/examples/fleet-connector)
- **Examples index**: [examples/README.md](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/README.md)

