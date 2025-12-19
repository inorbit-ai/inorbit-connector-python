<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Connector API

This page specifies the connector base classes you subclass to build connectors.

## `FleetConnector`

`inorbit_connector.connector.FleetConnector` is the base class for connectors that manage multiple robots.

(spec-connector-fleetconnector-connect)=
### `_connect()`

**Override.**

Called once on startup (inside the connector’s background thread / event loop), before robot sessions are initialized.

Typical responsibilities:

- Connect to your fleet manager / backend services.
- Optionally fetch the fleet membership and call `update_fleet()` **before** sessions are created.
- Start background polling tasks that keep fresh state for all robots.

(spec-connector-fleetconnector-execution-loop)=
### `_execution_loop()`

**Override.**

Called repeatedly until stopped. The loop is rate-limited by `config.update_freq`, but it will never run faster than the body can execute.

Typical responsibilities:

- For each robot in `self.robot_ids`, fetch the latest state (often from background polling state) and publish data via the `publish_robot_*` methods.
- Handle exceptions inside the loop when possible (the framework logs and continues on exceptions).

(spec-connector-fleetconnector-disconnect)=
### `_disconnect()`

**Override.**

Called once during shutdown, after Edge SDK sessions are disconnected. Use this to stop polling tasks, close sockets, and release resources.

(spec-connector-fleetconnector-command-handler)=
### `_inorbit_robot_command_handler(robot_id, command_name, args, options)`

**Override.**

Called when a command arrives from InOrbit for a specific robot in the fleet.

Contract:

- `options["result_function"](...)` must be called to report success/failure, or you may raise `CommandFailure` for structured failure reporting.

See {doc}`../usage/commands-handling` for the full command result contract.

(spec-connector-fleetconnector-fetch-robot-map)=
### `fetch_robot_map(robot_id, frame_id) -> MapConfigTemp | None`

**Optional override.**

If `publish_robot_pose()` references a `frame_id` that is not present in `config.maps`, the framework schedules an async fetch:

- Calls your `fetch_robot_map()` coroutine.
- If you return a `MapConfigTemp` containing `image` bytes and metadata, the framework writes the image to a temporary file and inserts a corresponding `MapConfig` into `config.maps`.
- Then it publishes the map via `publish_robot_map()`.

Return `None` if the map can’t be fetched.

(spec-connector-fleetconnector-is-online)=
### `_is_fleet_robot_online(robot_id) -> bool`

**Optional override.**

The Edge SDK uses this callback to determine if a robot should be considered online. Default implementation returns `True`.

(spec-connector-fleetconnector-lifecycle)=
### `start()` / `join()` / `stop()`

**Callable.**

- `start()` creates a background thread and runs the connector lifecycle in an asyncio event loop.
- `join()` blocks until the background thread exits.
- `stop()` signals the event loop to stop and waits briefly for shutdown.

(spec-connector-fleetconnector-fleet-management)=
### `robot_ids` / `update_fleet(fleet)`

**Callable.**

- `robot_ids` is a cached list of robot IDs from `config.fleet`.
- `update_fleet()` updates `config.fleet` and refreshes `robot_ids`.

This is designed to be used during `_connect()` when your fleet membership comes from an external system.

(spec-connector-fleetconnector-publish-robot-pose)=
### `publish_robot_pose(robot_id, x, y, yaw, frame_id=None, **kwargs)`

**Callable.**

Publishes pose for one robot. If the `frame_id` differs from the last published `frame_id` for that robot, the framework triggers `publish_robot_map(..., is_update=True)`.

(spec-connector-fleetconnector-publish-robot-map)=
### `publish_robot_map(robot_id, frame_id, is_update=False)`

**Callable.**

- If `frame_id` exists in `config.maps`, publishes the configured map to InOrbit.
- Otherwise schedules an async fetch via `fetch_robot_map()` (see above).

(spec-connector-fleetconnector-publish-robot-odometry)=
### `publish_robot_odometry(robot_id, **kwargs)`

**Callable.** Publishes odometry data for one robot.

(spec-connector-fleetconnector-publish-robot-key-values)=
### `publish_robot_key_values(robot_id, **kwargs)`

**Callable.** Publishes key-value telemetry for one robot.

(spec-connector-fleetconnector-publish-robot-system-stats)=
### `publish_robot_system_stats(robot_id, **kwargs)`

**Callable.** Publishes system stats for one robot.

(spec-connector-fleetconnector-get-robot-session)=
### `_get_robot_session(robot_id) -> RobotSession`

**Callable (advanced).**

Returns the underlying Edge SDK session for `robot_id`. Use this if you need Edge SDK functionality that is not wrapped by this package.

## `Connector`

`inorbit_connector.connector.Connector` is a single-robot specialization of `FleetConnector`. It selects a single robot out of the fleet config and provides convenience wrappers that omit `robot_id`.

(spec-connector-connector-lifecycle-hooks)=
### Lifecycle hooks

**Override.** Same intent as fleet:

- `_connect()`
- `_execution_loop()`
- `_disconnect()`

(spec-connector-connector-command-handler)=
### `_inorbit_command_handler(command_name, args, options)`

**Override.**

Single-robot command handler. It is called through the fleet-level handler internally, but without requiring you to accept `robot_id`.

(spec-connector-connector-fetch-map)=
### `fetch_map(frame_id) -> MapConfigTemp | None`

**Optional override.**

Single-robot convenience for map fetching. The framework uses it by delegating `fetch_robot_map()` to `fetch_map()`.

(spec-connector-connector-is-online)=
### `_is_robot_online() -> bool`

**Optional override.**

Single-robot convenience for online status. The fleet-level online check delegates to this method.

(spec-connector-connector-publishing)=
### Publishing wrappers

**Callable.** Single-robot wrappers over the fleet publishing methods:

- `publish_pose(...)` / `publish_map(...)`
- `publish_odometry(...)`
- `publish_key_values(...)`
- `publish_system_stats(...)`

(spec-connector-connector-get-session)=
### `_get_session() -> RobotSession`

**Callable (advanced).**

Returns the underlying Edge SDK session for the current robot.

### Deprecated: `_robot_session`

`Connector._robot_session` is deprecated; use `_get_session()` instead.


