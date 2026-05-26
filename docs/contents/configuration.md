---
title: "Configuration"
description: "Configuration models and file formats for connectors"
---

The `inorbit-connector` framework uses Pydantic models for configuration, providing validation and type safety.

## ConnectorConfig

The main configuration class is `ConnectorConfig`, which contains all settings for your connector. It includes a `fleet` field containing a list of `RobotConfig` entries.

Connectors should subclass `inorbit_connector.models.ConnectorConfig` and define a `connector_config` field that contains the configuration for the connector. For more details see the [Creating a Custom Configuration](#creating-a-custom-configuration) section below.

### Key Fields

- **`api_key`** (str | None): The InOrbit API key. Can be set via environment variable `INORBIT_API_KEY`
- **`api_url`** (HttpUrl): The URL of the InOrbit API endpoint. Defaults to InOrbit Cloud SDK URL. Can be set via environment variable `INORBIT_API_URL`
- **`connector_type`** (str): A string identifier for your connector type (e.g., "example_bot"). This value is also automatically published to InOrbit as a robot key-value on session init. See [Automatic `connector_type` publishing](publishing.md#automatic-connector-type-publishing).
- **`connector_config`** (BaseModel): Your custom configuration model that inherits from Pydantic's `BaseModel`. This is where you define connector-specific fields
- **`update_freq`** (float): Update frequency in Hz for the execution loop. Default is 1.0
- **`location_tz`** (str): The timezone of the robot location (e.g., "America/Los_Angeles", "UTC"). Must be a valid pytz timezone
- **`logging`** (LoggingConfig): Logging configuration (see below)
- **`maps`** (dict[str, MapConfig]): Dictionary mapping frame_id to map configuration (see below)
- **`env_vars`** (dict[str, str]): Environment variables to be set in the connector or user scripts
- **`fleet`** (list[RobotConfig]): List of robot configurations (see below)
- **`user_scripts_dir`** (DirectoryPath | None): Path to directory containing user scripts for command execution
- **`account_id`** (str | None): InOrbit account ID, required for publishing footprints
- **`inorbit_robot_key`** (str | None): Robot key for InOrbit Connect robots. See [API documentation](https://api.inorbit.ai/docs/index.html#operation/generateRobotKey)
- **`metrics`** (MetricsConfig): Optional Prometheus metrics endpoint. Disabled by default. See [Metrics](usage/metrics) for the full guide and [`MetricsConfig`](#metricsconfig) for the field list.

### Environment Variables

The following environment variables are automatically read during configuration:

- **`INORBIT_API_KEY`** (required): The InOrbit API key
- **`INORBIT_API_URL`** (optional): The InOrbit API endpoint URL

## RobotConfig

Represents configuration for a single robot in the fleet:

- **`robot_id`** (str): The InOrbit robot ID
- **`cameras`** (list[CameraConfig]): List of camera configurations for this robot

## MapConfig

Configuration for a map that can be associated with a frame_id:

- **`file`** (FilePath): Path to the PNG map file
- **`map_id`** (str): The map identifier
- **`map_label`** (str, optional): Human-readable map label
- **`origin_x`** (float): X coordinate of the map origin
- **`origin_y`** (float): Y coordinate of the map origin
- **`resolution`** (float): Map resolution in meters per pixel
- **`format_version`** (int, optional): Default is 2. A value of 1 indicates the Y axis is inverted while a value of 2 indicates natural map rendering. See https://developer.inorbit.ai/docs#maps

## LoggingConfig

Configuration for logging:

- **`config_file`** (FilePath | None): Path to logging configuration file. If not set, uses default configuration
- **`log_level`** (LogLevels | None): Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Overrides the level set in the config file
- **`defaults`** (dict[str, str]): Default values to pass to the logging configuration file (e.g., log file path)

## MetricsConfig

Optional Prometheus metrics endpoint. When `enabled` is `false` (the default) no HTTP server is started and all instruments are no-ops. See [Metrics](usage/metrics) for the user guide.

- **`enabled`** (bool): Master switch. Default is `false`
- **`bind_host`** (str): HTTP server bind address. Default is `0.0.0.0`
- **`bind_port`** (int): HTTP server TCP port. Default is `9090`. Use `0` to let the OS pick an ephemeral free port
- **`advertise_host`** (str | None): Hostname written to the discovery file. Defaults to `socket.gethostname()`
- **`discovery_dir`** (Path | None): Directory where the connector writes a Prometheus `file_sd`-format JSON file describing its endpoint. Auto-created. Default is `/var/run/inorbit-metrics`. Set to `null` (in YAML) / `None` (in Python) to skip writing the discovery file when the scraper already knows the connector's host and port.
- **`connector_id`** (str | None): Unique-per-host identifier. Used as the OTEL `service.instance.id` resource attribute and as the discovery filename. Defaults to `socket.gethostname()`
- **`exporter_namespace`** (str): Prefix prepended to every Prometheus metric name. ASCII identifier (no hyphens). Default is `"inorbit_connector"`
- **`extra_resource_attributes`** (dict[str, str]): Static OTEL Resource attributes added to every metric (low-cardinality only). Default is `{}`

(creating-a-custom-configuration)=
## Creating a Custom Configuration

To create a connector-specific configuration, subclass `ConnectorConfig`:

```python
from pydantic import BaseModel
from inorbit_connector.models import ConnectorConfig, RobotConfig

class MyRobotConfig(BaseModel):
    """Custom fields for your robot."""
    api_version: str
    hardware_revision: str
    custom_setting: str

class MyConnectorConfig(ConnectorConfig):
    """Configuration for your connector."""
    connector_config: MyRobotConfig
    
    @field_validator("connector_type")
    def check_connector_type(cls, connector_type: str) -> str:
        if connector_type != "my_connector":
            raise ValueError(f"Expected connector type 'my_connector'")
        return connector_type
```

## Configuration Files

Configuration is typically loaded from YAML files. See:
- Single robot: [`examples/example.yaml`](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/example.yaml)
- Fleet: [`examples/example.fleet.yaml`](https://github.com/inorbit-ai/inorbit-connector-python/blob/main/examples/example.fleet.yaml)

Use `inorbit_connector.utils.read_yaml()` to load configuration from YAML files:

```python
from inorbit_connector.utils import read_yaml

yaml_data = read_yaml("config.yaml")
config = MyConnectorConfig(**yaml_data)
```
