# Single-Robot Connector

Subclass `inorbit_connector.connector.Connector` and implement:

- `_connect()`: set up external services
- `_execution_loop()`: publish data periodically
- `_disconnect()`: clean up resources
- `_inorbit_command_handler(...)`: handle InOrbit commands

## Lifecycle

- `start()`: starts an async loop in a background thread
- `join()`: blocks until stopped
- `stop()`: signals stop and waits for shutdown

## Publishing

- `publish_pose(x, y, yaw, frame_id)` (auto-updates map on new `frame_id`)
- `publish_odometry(**kwargs)`
- `publish_key_values(**kwargs)`
- `publish_system_stats(**kwargs)`

## Examples

- Simple connector: [examples/simple-connector/connector.py](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/simple-connector/connector.py)
- Robot connector (CLI): [examples/robot-connector/](https://github.com/inorbit-ai/inorbit-connector-python/tree/main/examples/robot-connector)
- Examples index: [examples/README.md](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/README.md)

