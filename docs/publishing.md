<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Publishing Data

The connector framework provides methods to publish various types of data to InOrbit. Both single-robot (`Connector`) and fleet (`FleetConnector`) connectors support publishing, with fleet connectors using methods prefixed with `publish_robot_*` that require a `robot_id` parameter.

Publishing methods are mostly thin wrappers around `RobotSession` methods from the [InOrbit Edge SDK](https://github.com/inorbit-ai/inorbit-edge-sdk-python), except for the `publish_pose()` and `publish_map()` methods which include additional map handling logic.

## Pose and Map

### Single-Robot Connectors

```python
publish_pose(x: float, y: float, yaw: float, frame_id: str, **kwargs) -> None
```

Publishes a pose to InOrbit. If the `frame_id` is different from the last published frame_id, the map metadata is automatically sent via `publish_map()`.

**Parameters:**
- `x` (float): X coordinate
- `y` (float): Y coordinate
- `yaw` (float): Yaw angle in radians
- `frame_id` (str): Frame ID for the pose. If this frame_id exists in the maps configuration, the map will be automatically uploaded
- `**kwargs`: Additional arguments for pose publishing

```python
publish_map(frame_id: str, is_update: bool = False) -> None
```

Manually publish map metadata. Usually called automatically when `frame_id` changes in `publish_pose()`.

**Parameters:**
- `frame_id` (str): The frame ID of the map (must exist in configuration maps)
- `is_update` (bool): Whether this is an update to an existing map

### Fleet Connectors

```python
publish_robot_pose(robot_id: str, x: float, y: float, yaw: float, frame_id: str = None, **kwargs) -> None
```

Publishes a pose for a specific robot. Automatically updates map when `frame_id` changes.

```python
publish_robot_map(robot_id: str, frame_id: str, is_update: bool = False) -> None
```

Manually publish map metadata for a specific robot.

## Telemetry

### Odometry

**Single-Robot:**
```python
publish_odometry(**kwargs) -> None
```

**Fleet:**
```python
publish_robot_odometry(robot_id: str, **kwargs) -> None
```

Publishes odometry data to InOrbit. Common fields include:
- `linear_speed`: Linear velocity
- `angular_speed`: Angular velocity
- `linear_acceleration`: Linear acceleration
- `angular_acceleration`: Angular acceleration

### Key-Value Pairs

**Single-Robot:**
```python
publish_key_values(**kwargs) -> None
```

**Fleet:**
```python
publish_robot_key_values(robot_id: str, **kwargs) -> None
```

Publishes key-value pairs as telemetry data. These can represent any custom robot state or metrics.

**Example:**
```python
self.publish_key_values(
    battery_level=85.5,
    status="idle",
    current_mission="delivery_1",
    temperature=23.4
)
```

### System Statistics

**Single-Robot:**
```python
publish_system_stats(**kwargs) -> None
```

**Fleet:**
```python
publish_robot_system_stats(robot_id: str, **kwargs) -> None
```

Publishes system statistics such as CPU, RAM, and disk usage.

**Example:**
```python
self.publish_system_stats(
    cpu_load_percentage=45.2,
    ram_usage_percentage=62.8,
    hdd_usage_percentage=34.1
)
```

## Cameras

Cameras are configured in the `RobotConfig.cameras` field and are automatically registered when the connector connects.

### Camera Configuration

Cameras are configured using `CameraConfig` from the InOrbit Edge SDK. Each camera in the `RobotConfig.cameras` list is automatically registered with InOrbit.

**Example configuration:**
```yaml
fleet:
  - robot_id: my-robot
    cameras:
      - video_url: "rtsp://camera.example.com/stream"
        camera_id: "front_camera"
      - video_url: "http://camera.example.com/feed"
        camera_id: "back_camera"
```

Camera feeds are registered automatically during the `_connect()` phase, so no additional code is needed in your connector implementation.

## Publishing Best Practices

1. **Pose Updates**: Publish pose updates regularly in your `_execution_loop()` method
2. **Map Updates**: Maps are automatically updated when the `frame_id` changes. Ensure all frame_ids used in poses are defined in your configuration
3. **Telemetry Frequency**: Use the `update_freq` configuration to control how often your execution loop runs
4. **Error Handling**: Wrap publishing calls in try-except blocks to handle network errors gracefully
5. **Async Operations**: Use `asyncio.gather()` to publish multiple data types concurrently for better performance

**Example:**
```python
async def _execution_loop(self) -> None:
    # Fetch data from robot API
    pose_data = await self._get_robot_pose()
    telemetry_data = await self._get_robot_telemetry()
    
    # Publish data
    self.publish_pose(
        pose_data['x'],
        pose_data['y'],
        pose_data['yaw'],
        pose_data['frame_id']
    )
    
    self.publish_key_values(**telemetry_data)
```
