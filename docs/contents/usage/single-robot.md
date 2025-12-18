<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Single-Robot Connector

Subclass `inorbit_connector.connector.Connector` to create a connector for a single robot.

## Constructor

```python
def __init__(self, robot_id: str, config: ConnectorConfig, **kwargs) -> None
```

**Parameters:**
- `robot_id` (str): The InOrbit robot ID
- `config` (ConnectorConfig): The connector configuration

**Keyword Arguments:**
- `register_user_scripts` (bool): Automatically register user scripts. Default: `False`
- `default_user_scripts_dir` (str): Default directory for user scripts. Default: `~/.inorbit_connectors/connector-{robot_id}/local/`
- `create_user_scripts_dir` (bool): Create the user scripts directory if it doesn't exist. Default: `False`
- `register_custom_command_handler` (bool): Automatically register the command handler. Default: `True`

## Required Methods

Subclasses must implement the following abstract methods:

### `_connect()`

Set up external services and connections. This is called once when the connector starts, before the execution loop begins.

```python
@override
async def _connect(self) -> None:
    """Connect to robot services."""
    # Initialize robot API client and/or other related services
    # e.g. initialize a REST API client and start a polling loop 
    pass
```

### `_execution_loop()`

The main execution loop that runs periodically. This is where you fetch robot data and publish it to InOrbit.

Refer to the [publishing guide](../publishing) for more details on publishing data to InOrbit.

With polling-based connectors, it is advisable to run polling loops concurrently with the execution loop to avoid long running `_execution_loop` calls. See the [robot-connector](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/robot-connector/connector.py) and [fleet-connector](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/simple-fleet-connector/connector.py) examples for more details.

```python
@override
async def _execution_loop(self) -> None:
    """Main execution loop."""
    # Fetch robot pose
    pose = await self._get_robot_pose()
    self.publish_pose(pose.x, pose.y, pose.yaw, pose.frame_id)
    
    # Fetch and publish telemetry
    telemetry = await self._get_robot_telemetry()
    self.publish_key_values(**telemetry)
```

The loop runs at the frequency specified by `config.update_freq` (default: 1.0 Hz).

### `_disconnect()`

Clean up resources and disconnect from external services. This is called when the connector stops.

```python
@override
async def _disconnect(self) -> None:
    """Disconnect from robot services."""
    # Close robot API connections
    # Clean up resources
    pass
```

### `_inorbit_command_handler()`

:::{hint}
See the [Commands Handling](commands-handling) chapter for more details.
:::

Handle commands received from InOrbit. This method is automatically registered if `register_custom_command_handler` is True (default).

```python
from inorbit_connector.connector import CommandResultCode, CommandFailure

@override
async def _inorbit_command_handler(
    self, command_name: str, args: list, options: dict
) -> None:
    """Handle InOrbit commands."""
    if command_name == "start_mission":
        result = await self._robot.start_mission(args[0])
        if result:
            options["result_function"](CommandResultCode.SUCCESS)
        else:
            raise CommandFailure(
                execution_status_details="Mission start failed",
                stderr="Robot returned error code"
            )
```

Exceptions raised in the command handler are automatically caught and reported. Use `CommandFailure` to provide specific error details that will be displayed in InOrbit's audit logs and action execution details.

## Lifecycle Methods

### `start()`

Starts the connector in a background thread. Creates an async event loop and begins the connection process.

```python
connector = MyConnector(robot_id, config)
connector.start()
```

### `join()`

Blocks until the connector thread finishes. Use this to keep your main thread alive.

```python
connector.join()
```

### `stop()`

Signals the connector to stop and waits for shutdown. This calls `_disconnect()` and cleans up resources.

```python
connector.stop()
```

## Publishing Methods

See the [Publishing Guide](../publishing) for detailed information on publishing methods.

## Advanced Methods

### `_get_session()`

Access the underlying `RobotSession` from the InOrbit Edge SDK for advanced use cases not covered by the connector API.

```python
def _get_session(self) -> RobotSession:
    """Get the edge-sdk robot session for the current robot."""
```

**Example:**
```python
async def _execution_loop(self) -> None:
    # Access the session directly for advanced features
    session = self._get_session()
    # Use Edge SDK methods directly
    ...
```

### `_is_robot_online()`

Override this method to provide custom robot health checks. The default implementation assumes the robot is online if the connector is running.

```python
def _is_robot_online(self) -> bool:
    """Check if the robot is online.
    
    Returns:
        bool: True if robot is online, False otherwise.
    """
```

**Example:**
```python
@override
def _is_robot_online(self) -> bool:
    """Check robot connectivity via API."""
    try:
        return self._robot_api.is_connected()
    except Exception:
        return False
```


## User Scripts

User scripts allow executing custom shell scripts from InOrbit. To enable:

1. Set `user_scripts_dir` in your configuration
2. Pass `register_user_scripts=True` to the constructor
3. Place `.sh` scripts in the user scripts directory

Scripts are automatically registered and can be executed from InOrbit.

## Examples

- **Simple connector**: [examples/simple-connector/connector.py](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/simple-connector/connector.py)
- **Robot connector (CLI)**: [examples/robot-connector/](https://github.com/inorbit-ai/inorbit-connector-python/tree/main/examples/robot-connector)
- **Examples index**: [examples/README.md](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/README.md)

