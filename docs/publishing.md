<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Publishing Data

## Pose and Map
- Call `publish_pose(x, y, yaw, frame_id)`.
- When `frame_id` changes, the map metadata is sent via `publish_map(...)`.

## Telemetry
- `publish_odometry(**kwargs)`
- `publish_key_values(**kwargs)`
- `publish_system_stats(**kwargs)`

## Cameras
- Configure cameras in `RobotConfig.cameras`.
- Feeds are registered at connect time.

