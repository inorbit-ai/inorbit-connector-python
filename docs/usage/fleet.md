# Fleet Connector

Subclass `inorbit_connector.connector.FleetConnector` to manage multiple robots.

- Access robot IDs via `self.robot_ids`
- Use per-robot methods:
  - `publish_robot_pose(robot_id, ...)`
  - `publish_robot_odometry(robot_id, ...)`
  - `publish_robot_key_values(robot_id, ...)`
  - `publish_robot_system_stats(robot_id, ...)`
- Command handler signature includes `robot_id`

## Examples

- Simple fleet connector: [examples/simple-fleet-connector/connector.py](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/simple-fleet-connector/connector.py)
- Fleet connector (CLI): [examples/fleet-connector/](https://github.com/inorbit-ai/inorbit-connector-python/tree/main/examples/fleet-connector)
- Examples index: [examples/README.md](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/README.md)

