---
title: "Models"
description: "Configuration models specification"
--- (configuration)

This page specifies the configuration models defined by `inorbit_connector.models`.

(spec-models-connectorconfig)=
## `ConnectorConfig`

Base configuration model for connectors.

Key points:

- You typically **subclass** this to define your connector-specific `connector_config` model.
- The base model reads `INORBIT_API_KEY` and `INORBIT_API_URL` from environment variables by default.
- `fleet` must contain at least one `RobotConfig`, and robot IDs must be unique.

### `to_singular_config(robot_id) -> ConnectorConfig`

Returns a config instance of the same subclass type, with `fleet` filtered down to exactly the requested robot.

### Deprecated: `log_level`

`ConnectorConfig.log_level` is deprecated in favor of `ConnectorConfig.logging.log_level`.

(spec-models-robotconfig)=
## `RobotConfig`

Per-robot configuration:

- `robot_id`: the InOrbit robot ID.
- `cameras`: list of Edge SDK `CameraConfig` objects. Camera registration is performed automatically during connector startup.

(spec-models-mapconfig)=
## `MapConfig` / `MapConfigTemp`

These models describe map metadata and image source.

- `MapConfig`: file-backed map with `file: FilePath` pointing to a `.png`.
- `MapConfigTemp`: in-memory map payload with `image: bytes`.

Both carry metadata via `MapConfigBase`:

- `map_id`, optional `map_label`
- `origin_x`, `origin_y`, `resolution`
- `format_version` (must be 1 or 2)

(spec-models-loggingconfig)=
## `LoggingConfig`

Logging configuration used by the connector at startup:

- `config_file`: path to a logging config file (defaults to the package’s `logging.default.conf`).
- `log_level`: optional override for the root logger level.
- `defaults`: dictionary passed to the logging config (e.g. `log_file`).

See [setup_logger()](/ground-control/robot-integration/connector-framework/specification/logging#spec-logging-setup-logger) for how it is applied.

## Deprecated: `InorbitConnectorConfig`

`InorbitConnectorConfig` is a deprecated single-robot configuration format. It can be converted to a fleet config via:

- `to_fleet_config(robot_id) -> ConnectorConfig`

New implementations should use `ConnectorConfig` directly.


