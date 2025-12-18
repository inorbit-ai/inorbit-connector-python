<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Specification

This section specifies the public surface of the `inorbit-connector` package: what you are expected to **override** when implementing a connector, and what you can **call** at runtime.

## Intended usage

An InOrbit connector is an application that:

- Connects to your robot (or fleet manager) and to InOrbit via the InOrbit Edge SDK.
- Runs a periodic execution loop to publish telemetry (pose, odometry, key-values, system stats).
- Optionally handles commands coming from InOrbit.

You typically:

- Implement a **single-robot** connector by subclassing `inorbit_connector.connector.Connector`.
- Implement a **fleet** connector by subclassing `inorbit_connector.connector.FleetConnector`.

At runtime, you call:

- `start()` to spawn the connector thread and begin the async lifecycle.
- `join()` to block the main thread until shutdown.
- `stop()` to request shutdown.

During the lifecycle, the framework calls your overrides:

- `_connect()` once at startup (before sessions are initialized).
- `_execution_loop()` repeatedly at approximately `config.update_freq` Hz.
- `_disconnect()` once at shutdown.
- A command handler (`_inorbit_command_handler()` for single-robot; `_inorbit_robot_command_handler()` for fleet) when commands arrive.

For map handling, `publish_pose()` / `publish_robot_pose()` automatically trigger map publication when the `frame_id` changes. If a map is not configured, the connector can fetch it by overriding `fetch_map()` / `fetch_robot_map()`.

For narrative guides, see:

- Single robot: [Single-Robot Connector](../usage/single-robot.md)
- Fleet: [Fleet Connector](../usage/fleet.md)
- Commands: [Commands Handling](../usage/commands-handling.md)
- Publishing: [Publishing Data](../publishing.md)
- Configuration: [Configuration](../configuration.md)

## API surface (callable + overridable)

The table below lists package-defined symbols meant for direct use (call) or extension (override). Each row links to a longer specification page.

| Kind | Symbol | Purpose | Details |
| --- | --- | --- | --- |
| Override | `FleetConnector._connect()` | Connect to external services (fleet manager, robot backends) before sessions initialize. | [Details](connector.md#spec-connector-fleetconnector-connect) |
| Override | `FleetConnector._execution_loop()` | Periodic loop; publish telemetry for each robot. | [Details](connector.md#spec-connector-fleetconnector-execution-loop) |
| Override | `FleetConnector._disconnect()` | Shutdown external services and release resources. | [Details](connector.md#spec-connector-fleetconnector-disconnect) |
| Override | `FleetConnector._inorbit_robot_command_handler()` | Handle commands for a specific `robot_id`. | [Details](connector.md#spec-connector-fleetconnector-command-handler) |
| Override (optional) | `FleetConnector.fetch_robot_map()` | Fetch a missing map (bytes + metadata) when publishing pose refers to an unknown `frame_id`. | [Details](connector.md#spec-connector-fleetconnector-fetch-robot-map) |
| Override (optional) | `FleetConnector._is_fleet_robot_online()` | Provide robot online status; used by Edge SDK callback. | [Details](connector.md#spec-connector-fleetconnector-is-online) |
| Call | `FleetConnector.start()` / `join()` / `stop()` | Run and control the connector lifecycle. | [Details](connector.md#spec-connector-fleetconnector-lifecycle) |
| Call | `FleetConnector.update_fleet()` / `FleetConnector.robot_ids` | Update fleet configuration (typically during `_connect()`) and access robot IDs. | [Details](connector.md#spec-connector-fleetconnector-fleet-management) |
| Call | `FleetConnector.publish_robot_pose()` | Publish pose; triggers map publish when `frame_id` changes. | [Details](connector.md#spec-connector-fleetconnector-publish-robot-pose) |
| Call | `FleetConnector.publish_robot_map()` | Publish map metadata/image from configured maps (or after fetch). | [Details](connector.md#spec-connector-fleetconnector-publish-robot-map) |
| Call | `FleetConnector.publish_robot_odometry()` | Publish odometry. | [Details](connector.md#spec-connector-fleetconnector-publish-robot-odometry) |
| Call | `FleetConnector.publish_robot_key_values()` | Publish key-value telemetry. | [Details](connector.md#spec-connector-fleetconnector-publish-robot-key-values) |
| Call | `FleetConnector.publish_robot_system_stats()` | Publish system stats telemetry. | [Details](connector.md#spec-connector-fleetconnector-publish-robot-system-stats) |
| Call (advanced) | `FleetConnector._get_robot_session()` | Access the underlying Edge SDK `RobotSession` for a specific robot. | [Details](connector.md#spec-connector-fleetconnector-get-robot-session) |
| Override | `Connector._connect()` / `_execution_loop()` / `_disconnect()` | Same lifecycle hooks as fleet, for a single robot. | [Details](connector.md#spec-connector-connector-lifecycle-hooks) |
| Override | `Connector._inorbit_command_handler()` | Handle commands for the single robot. | [Details](connector.md#spec-connector-connector-command-handler) |
| Override (optional) | `Connector.fetch_map()` | Fetch a missing map for the current robot when pose references an unknown `frame_id`. | [Details](connector.md#spec-connector-connector-fetch-map) |
| Override (optional) | `Connector._is_robot_online()` | Provide online status for the current robot. | [Details](connector.md#spec-connector-connector-is-online) |
| Call | `Connector.publish_pose()` / `publish_map()` | Publish pose/map for the current robot (map handling included). | [Details](connector.md#spec-connector-connector-publishing) |
| Call | `Connector.publish_odometry()` / `publish_key_values()` / `publish_system_stats()` | Publish telemetry for the current robot. | [Details](connector.md#spec-connector-connector-publishing) |
| Call (advanced) | `Connector._get_session()` | Access the underlying Edge SDK `RobotSession` for the current robot. | [Details](connector.md#spec-connector-connector-get-session) |
| Type | `ConnectorConfig` | Base configuration model for connectors. | [Details](models.md#spec-models-connectorconfig) |
| Type | `RobotConfig` | Per-robot configuration (robot_id + cameras). | [Details](models.md#spec-models-robotconfig) |
| Type | `MapConfig` / `MapConfigTemp` | Map configuration (file-backed vs in-memory bytes) used by map publishing/fetching. | [Details](models.md#spec-models-mapconfig) |
| Type | `LoggingConfig` / `LogLevels` | Logging configuration and log-level enum. | [Details](logging.md#spec-logging-loggingconfig) |
| Call | `read_yaml()` | Load YAML configuration data (with deprecated `robot_id` selection support). | [Details](utils.md#spec-utils-readyaml) |
| Type / Call | `CommandResultCode` / `CommandFailure` | Standard command result code enum and structured failure exception. | [Details](commands.md#spec-commands-commandfailure) |
| Call | `parse_custom_command_args()` | Parse custom-command args (RunScript action payload) into `(script_name, params)`. | [Details](commands.md#spec-commands-parse-custom-command-args) |
| Type | `CommandModel` / `ExcludeUnsetMixin` | Pydantic-based command argument validation utilities. | [Details](commands.md#spec-commands-commandmodel) |
| Call | `setup_logger()` | Configure logging from `LoggingConfig`. | [Details](logging.md#spec-logging-setup-logger) |
| Type | `ConditionalColoredFormatter` | Optional `colorlog`-backed formatter used by the default logging config. | [Details](logging.md#spec-logging-conditional-colored-formatter) |

## Pages

- [Connector API](connector.md)
- [Models (configuration)](models.md)
- [Commands utilities](commands.md)
- [Utilities](utils.md)
- [Logging](logging.md)


