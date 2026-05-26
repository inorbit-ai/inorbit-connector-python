---
title: "Models"
description: "Configuration models specification"
--- (configuration)

This page specifies the configuration models defined by `inorbit_connector.models`.

(spec-models-connectorrootconfig)=
## `ConnectorRootConfig`

Top-level configuration model for connectors. Subclasses `BaseSettings` from pydantic-settings.

Key points:

- You typically **subclass** this and narrow the `connector_config` field to a concrete `ConnectorSpecificConfig` subclass.
- Resolves `INORBIT_*` environment variables and reads `config/.env` at instantiation time via pydantic-settings. Init kwargs (typically values from a YAML file) take precedence over env vars.
- `fleet` must contain at least one `RobotConfig`, and robot IDs must be unique.

### `to_singular_config(robot_id) -> ConnectorRootConfig`

Returns a config instance of the same subclass type, with `fleet` filtered down to exactly the requested robot.

(spec-models-connectorspecificconfig)=
## `ConnectorSpecificConfig`

Base class for per-connector vendor configuration. Subclasses `BaseSettings` from pydantic-settings.

Subclass this and set the `CONNECTOR_TYPE` class variable. The framework automatically configures env-var loading with the prefix `INORBIT_{CONNECTOR_TYPE}_` and reads `config/.env`.

```python
from inorbit_connector.models import ConnectorSpecificConfig

class AcmeConfig(ConnectorSpecificConfig):
    CONNECTOR_TYPE = "acme"

    fleet_host: str
    fleet_api_key: str = "default"
```

With this definition, `INORBIT_ACME_FLEET_HOST` and `INORBIT_ACME_FLEET_API_KEY` are resolved from the environment. Init kwargs take precedence over env vars.

Connectors with custom env-loading needs (e.g. per-robot prefixes) can subclass `BaseSettings` directly instead.

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

See [setup_logger()](logging.md#spec-logging-setup-logger) for how it is applied.
