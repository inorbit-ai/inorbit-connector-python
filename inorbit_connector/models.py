#!/usr/bin/env python

# Copyright 2024 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import os
import re
from pathlib import Path
from typing import List, Optional

# Third-party
import pytz
from inorbit_edge.models import CameraConfig
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
from pydantic import (
    BaseModel,
    ConfigDict,
    DirectoryPath,
    Field,
    FilePath,
    HttpUrl,
    field_validator,
)

# InOrbit
from inorbit_connector.utils import DEFAULT_LOGGING_CONFIG, DEFAULT_TIMEZONE
from inorbit_connector.logging.logger import LogLevels


class MapConfigBase(BaseModel):
    """Base class for map configuration with common metadata fields.

    Attributes:
        map_id (str): The map id
        map_label (str, optional): The map label
        origin_x (float): The x origin of the map
        origin_y (float): The y origin of the map
        resolution (float): The resolution
        format_version (int): Map format version. Refer to
            https://developer.inorbit.ai/docs#maps
    """

    map_id: str
    map_label: Optional[str] = None
    origin_x: float
    origin_y: float
    resolution: float
    format_version: int = 2

    @field_validator("format_version")
    def validate_format_version(cls, v: int) -> int:
        """Validate that the format version is 1 or 2.

        Args:
            v (int): The format version to be validated

        Raises:
            ValueError: If the format version is not 1 or 2
        """
        if v not in (1, 2):
            raise ValueError("format_version must be 1 or 2")
        return v


class MapConfig(MapConfigBase):
    """Map configuration with file path for stored maps.

    Attributes:
        file (FilePath): The path to the PNG map file
    """

    file: FilePath

    @field_validator("file")
    def validate_png_file(cls, file: FilePath) -> FilePath:
        """Validate that the file is a PNG file.

        Args:
            file (FilePath): The path to the file to be validated

        Raises:
            ValueError: If the file is not a PNG file

        Returns:
            FilePath: The given file path if it is a PNG file
        """
        if file.suffix.lower() != ".png":
            raise ValueError("The map file must be a PNG file")
        return file


class MapConfigTemp(MapConfigBase):
    """Temporary map configuration with in-memory image bytes.

    Used for fetching maps from the robot before writing to a temporary file.

    Attributes:
        image (bytes): The map image data in memory
    """

    image: bytes


class LoggingConfig(BaseModel):
    """Class representing a logging configuration.

    Attributes:
        config_file (FilePath | None, optional): The path to the logging configuration
           file. If not set, the default configuration file will be used.
        log_level (LogLevels | None, optional): The log level. Overwrites the log level
            set in the logging configuration file.
        defaults (dict[str, str], optional): The log defaults to pass down to the
            logging configuration file.
    """

    config_file: FilePath | None = DEFAULT_LOGGING_CONFIG
    log_level: LogLevels | None = None
    defaults: dict[str, str] = {
        "log_file": "inorbit-connector.log",
    }


_METRICS_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class MetricsConfig(BaseModel):
    """Configuration for the Prometheus-exported metrics server.

    When ``enabled`` is True, the connector installs a process-global OTEL
    MeterProvider with a PrometheusMetricReader and starts an HTTP server
    serving ``/metrics`` on ``bind_host:bind_port``. It also writes a
    Prometheus ``file_sd`` JSON file under ``discovery_dir`` so a host-side
    OTEL collector can discover and scrape the endpoint. Set
    ``discovery_dir`` to ``None`` to disable the discovery file (useful when
    the scraper already knows the connector's host and port).

    When ``enabled`` is False (the default), no server is started and all
    instrument calls are silently dropped by the OTEL no-op provider.

    Identity labels set on every exported metric: ``service.name``,
    ``service.instance.id``, ``service.version``, ``inorbit.connector.type``,
    ``inorbit.connector.id``, plus any key/value from
    ``extra_resource_attributes``.
    """

    enabled: bool = False
    bind_host: str = "0.0.0.0"
    bind_port: int = 9090
    advertise_host: Optional[str] = None
    discovery_dir: Optional[Path] = Path("/var/run/inorbit-metrics")
    connector_id: Optional[str] = None
    exporter_namespace: Optional[str] = None
    extra_resource_attributes: dict[str, str] = {}

    @field_validator("exporter_namespace")
    @classmethod
    def _validate_exporter_namespace(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not _METRICS_IDENTIFIER_RE.fullmatch(value):
            raise ValueError(
                "exporter_namespace must match [A-Za-z_][A-Za-z0-9_]* "
                "(no hyphens, no leading digit) for GCP/Prometheus compatibility"
            )
        return value

    @field_validator("extra_resource_attributes")
    @classmethod
    def _validate_extra_resource_attributes(
        cls, value: dict[str, str]
    ) -> dict[str, str]:
        for key, val in value.items():
            if not _METRICS_IDENTIFIER_RE.fullmatch(key):
                raise ValueError(
                    f"extra_resource_attributes key {key!r} must match "
                    "[A-Za-z_][A-Za-z0-9_]* (no hyphens)"
                )
            if not val:
                raise ValueError(
                    f"extra_resource_attributes[{key!r}] must be a non-empty string"
                )
        return value


class RobotConfig(BaseModel):
    """Class representing a robot configuration.

    Attributes:
        robot_id (str): The InOrbit ID of the robot
        cameras (list[CameraConfig]): The list of cameras
    """

    robot_id: str
    cameras: List[CameraConfig] = []


class ConnectorConfig(BaseModel):
    """Class representing an Inorbit connector model.

    This should not be instantiated on its own.

    A Connector specific configuration should be defined in a subclass adding the
    "connector_config" field.

    The following environment variables will be read during instantiation:

    * INORBIT_API_KEY (required): The InOrbit API key
    * INORBIT_API_URL: The URL of the API endpoint or inorbit_edge's
                       INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL by default

    in addition to those read by the Edge SDK during connector initialization.

    Attributes:
        api_key (str | None, optional): The InOrbit API key
        api_url (HttpUrl, optional): The URL of the API or inorbit_edge's
                                     INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL by default
        connector_type (str): The type of connector (see Class comment above)
        connector_config (BaseModel): The configuration for the connector
        use_websockets (bool, optional): If True, the underlying edge-sdk
            ``RobotSession`` connects to the InOrbit MQTT broker over the
            WebSockets transport instead of the default TCP transport. Combined
            with the edge-sdk's default ``use_ssl=True`` this yields a ``wss://``
            connection. Useful when the connector runs behind a firewall or
            proxy that only allows outbound HTTPS traffic. Default is False.
        update_freq (float, optional): Update frequency or 1 Hz by default
        location_tz (str, optional): The timezone of the location or "UTC" by default
        logging (LoggingConfig, optional): The logging configuration
        user_scripts_dir (DirectoryPath | None, optional): The location of custom user
            scripts
        account_id (str | None, optional): InOrbit account id, required for publishing
            footprints
        inorbit_robot_key (str | None, optional): Robot key for InOrbit Connect robots.
            See https://api.inorbit.ai/docs/index.html#operation/generateRobotKey
        maps (dict[str, MapConfig], optional): frame_id to map configuration mapping
        env_vars (dict[str, str], optional): Environment variables to be set in the
            connector or user scripts. The key is the environment variable name and the
            value is the value to set.
        fleet (list[RobotConfig]): The list of robot configurations.
    """

    model_config = ConfigDict(extra="forbid")

    api_key: str | None = os.getenv("INORBIT_API_KEY")
    # default_factory + explicit HttpUrl construction: handing a bare
    # string default to a `HttpUrl`-typed field stores it as `str` (the
    # type-coercion validator only runs on explicit inputs, not defaults),
    # which then trips Pydantic's serializer warning on every model_dump.
    api_url: HttpUrl = Field(
        default_factory=lambda: HttpUrl(
            os.getenv("INORBIT_API_URL", INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL)
        )
    )
    connector_type: str
    connector_config: BaseModel
    use_websockets: bool = False
    update_freq: float = 1.0
    location_tz: str = DEFAULT_TIMEZONE
    logging: LoggingConfig = LoggingConfig()
    user_scripts_dir: DirectoryPath | None = None
    account_id: str | None = None
    inorbit_robot_key: str | None = None
    maps: dict[str, MapConfig] = {}
    env_vars: dict[str, str] = {}
    metrics: MetricsConfig = MetricsConfig()
    fleet: list[RobotConfig]

    def to_singular_config(self, robot_id: str) -> "ConnectorConfig":
        """Filters out configurations not related to the given robot. The result is a
        config with a fleet field of length 1.

        Args:
            robot_id (str): The ID of the robot to filter the configuration for

        Returns:
            ConnectorConfig: The filtered configuration (preserves the subclass type)
        """
        # Filter the fleet first to validate robot_id exists
        filtered_fleet = [robot for robot in self.fleet if robot.robot_id == robot_id]

        if len(filtered_fleet) != 1:
            raise ValueError(
                f"Expected 1 robot configuration for robot {robot_id}, "
                f"got {len(filtered_fleet)}"
            )

        # Use self.__class__ to preserve the subclass type
        # (e.g., ExampleBotConnectorConfig)
        config = self.__class__(
            **self.model_dump(exclude={"fleet"}),
            fleet=filtered_fleet,
        )
        return config

    @field_validator("fleet")
    def must_contain_at_least_one_robot(
        cls, fleet: list[RobotConfig]
    ) -> list[RobotConfig]:
        """Validate that the fleet contains at least one robot.

        Args:
            fleet (list[RobotConfig]): The fleet configuration

        Returns:
            list[RobotConfig]: The fleet configuration
        """
        if len(fleet) < 1:
            raise ValueError("Fleet must contain at least one robot")
        return fleet

    @field_validator("fleet")
    def robot_ids_must_be_unique(cls, fleet: list[RobotConfig]) -> list[RobotConfig]:
        """Validate that the robot ids are unique.

        Args:
            fleet (list[RobotConfig]): The fleet configuration

        Returns:
            list[RobotConfig]: The fleet configuration
        """
        if len(set([robot.robot_id for robot in fleet])) != len(fleet):
            raise ValueError("Robot ids must be unique")
        return fleet

    @field_validator("api_key", "account_id")
    def check_whitespace(cls, value: str | None) -> str | None:
        """Check if the api_key contains whitespace.

        This is used for the api_key.

        Args:
            value (str | None): The api_key to be checked

        Raises:
            ValueError: If the api_key contains whitespace

        Returns:
            str | None: The given value if it does not contain whitespaces
        """
        if value is not None and any(char.isspace() for char in value):
            raise ValueError("Whitespaces are not allowed")
        return value

    @field_validator("location_tz")
    def location_tz_must_exist(cls, location_tz: str) -> str:
        """Validate the timezone exists in the pytz package.

        This will prevent instantiation if location_tz is not valid.

        Args:
            location_tz (str): A string representing the timezone location

        Returns:
            str: A string representing the validated timezone location

        Raises:
            ValueError: If the provided timezone location is not valid
        """
        if location_tz not in pytz.all_timezones:
            raise ValueError("Timezone must exist in pytz")
        return location_tz

    @field_validator("update_freq")
    def check_positive(cls, update_freq: float | None) -> float | None:
        """Check if an argument is positive and non-zero.

        This is used for the update_freq and scaling value.

        Args:
            update_freq (float): The frequency to be checked

        Raises:
            ValueError: If the frequency is less than or equal to zero

        Returns:
            float: The given frequency if it is positive and non-zero
        """
        if update_freq <= 0:
            raise ValueError("Must be positive and non-zero")
        return update_freq
