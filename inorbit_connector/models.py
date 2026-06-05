#!/usr/bin/env python

# Copyright 2024 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import re
from contextvars import ContextVar
from pathlib import Path
from typing import ClassVar, Generic, List, Optional, TypeVar

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

# Third-party
import pytz
from inorbit_edge.models import CameraConfig
from inorbit_edge.robot import (
    INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL,
    INORBIT_DEFAULT_API_URL,
)
from pydantic import (
    BaseModel,
    DirectoryPath,
    Field,
    FilePath,
    HttpUrl,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    EnvSettingsSource,
    DotEnvSettingsSource,
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

    When ``enabled`` is True, the connector installs a process-global OTel
    MeterProvider with a PrometheusMetricReader and starts an HTTP server
    serving ``/metrics`` on ``bind_host:bind_port``. It also writes a
    Prometheus ``file_sd`` JSON file under ``discovery_dir`` so a host-side
    OTel collector can discover and scrape the endpoint. Set
    ``discovery_dir`` to ``None`` to disable the discovery file (useful when
    the scraper already knows the connector's host and port).

    When ``enabled`` is False (the default), no server is started and all
    instrument calls are silently dropped by the OTel no-op provider.

    Identity labels set on every exported metric: ``service.name``,
    ``service.instance.id``, ``service.version``, ``inorbit.connector.type``,
    ``inorbit.connector.id``, plus any key/value from
    ``extra_resource_attributes``.

    The wire-level metric prefix is always ``inorbit_connector``; the
    connector type is exposed as the ``inorbit.connector.type`` Resource
    attribute, not as part of the metric name. This is intentional — see
    :mod:`inorbit_connector.metrics` for the rationale.
    """

    enabled: bool = False
    bind_host: str = "0.0.0.0"
    bind_port: int = 9090
    advertise_host: Optional[str] = None
    discovery_dir: Optional[Path] = Path("/var/run/inorbit-metrics")
    connector_id: Optional[str] = None
    extra_resource_attributes: dict[str, str] = {}

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


DEFAULT_ENV_FILE = "config/.env"


class ConnectorSpecificConfig(BaseSettings):
    """Base for per-connector vendor config.

    Subclasses set the CONNECTOR_TYPE class variable to get automatic
    env-var loading with prefix ``INORBIT_{CONNECTOR_TYPE}_``.

    Example::

        class ExampleBotConfig(ConnectorSpecificConfig):
            CONNECTOR_TYPE = "example_bot"
            example_bot_api_version: str
            example_bot_hw_rev: str

    Attributes:
        CONNECTOR_TYPE (ClassVar[str]): Connector identifier used to derive
            the env-var prefix.
    """

    CONNECTOR_TYPE: ClassVar[str]

    # Empty strings (e.g. from YAML placeholders) are ignored so they
    # don't override real defaults.  Unknown env vars are silently
    # discarded (extra="ignore") rather than raising or polluting the
    # model.  The env_file default is overridable at instantiation via
    # the ``_env_file`` kwarg.
    model_config = SettingsConfigDict(
        env_ignore_empty=True,
        case_sensitive=False,
        env_file=DEFAULT_ENV_FILE,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Use ``INORBIT_{CONNECTOR_TYPE}_`` as env-var prefix."""
        prefix = f"INORBIT_{cls.CONNECTOR_TYPE.upper()}_"
        common = dict(env_prefix=prefix, env_ignore_empty=True, case_sensitive=False)
        return (
            init_settings,
            EnvSettingsSource(settings_cls, **common),
            DotEnvSettingsSource(
                settings_cls, env_file=dotenv_settings.env_file, **common
            ),
            file_secret_settings,
        )


T = TypeVar("T", bound=ConnectorSpecificConfig)

# Thread-safe channel for forwarding ``_env_file`` from
# ConnectorRootConfig.__init__ to its "before" model validator.
_NOT_SET = object()
_env_file_var: ContextVar[object] = ContextVar("_env_file_var", default=_NOT_SET)


class ConnectorRootConfig(BaseSettings, Generic[T]):
    """Top-level InOrbit connector configuration.

    Reads ``INORBIT_*`` environment variables and ``config/.env`` at
    **instantiation time** via pydantic-settings.  Init kwargs (typically
    loaded from YAML) take precedence over env vars.

    Parametrize with a concrete ``ConnectorSpecificConfig`` subclass to
    get typed access to ``connector_config``::

        config = ConnectorRootConfig[MyConfig](**yaml_data)

    Subclassing is still supported for connectors that need root-level
    validators or additional fields.  Pass ``_env_file=None`` to disable
    dotenv reading for both root and nested config, or an explicit path
    to make both read from the same file.

    At least one of ``api_key`` or ``inorbit_robot_key`` must be provided.
    If neither is set (via init kwargs, environment variables, or dotenv),
    a ``ValidationError`` is raised at instantiation time.

    Attributes:
        api_key (str | None, optional): The InOrbit API key. Required unless
            ``inorbit_robot_key`` is provided.
        connection_config_url (HttpUrl, optional): The URL of the connection
            config endpoint or inorbit_edge's INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
            by default. Reads from ``INORBIT_CONNECTION_CONFIG_URL``.
        api_url (HttpUrl, optional): The URL of the InOrbit REST API or
            inorbit_edge's INORBIT_DEFAULT_API_URL by default. Reads from
            ``INORBIT_API_URL``.
        connector_type (str): The type of connector
        connector_config (ConnectorSpecificConfig): Vendor-specific configuration
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
        inorbit_robot_key (str | None, optional): Robot key for InOrbit Connect robots.
            Required unless ``api_key`` is provided.
            See https://api.inorbit.ai/docs/index.html#operation/generateRobotKey
        maps (dict[str, MapConfig], optional): frame_id to map configuration mapping
        env_vars (dict[str, str], optional): Environment variables to be set in the
            connector or user scripts. The key is the environment variable name and the
            value is the value to set.
        fleet (list[RobotConfig]): The list of robot configurations.
    """

    # All fields are resolvable from ``INORBIT_<FIELD>`` env vars or from
    # ``config/.env``.  Init kwargs (YAML) take highest precedence.
    # Unknown ``INORBIT_*`` vars are silently discarded (extra="ignore").
    model_config = SettingsConfigDict(
        env_prefix="INORBIT_",
        env_ignore_empty=True,
        case_sensitive=False,
        env_file=DEFAULT_ENV_FILE,
        extra="ignore",
    )

    api_key: str | None = None
    connection_config_url: HttpUrl = Field(
        default=HttpUrl(INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL),
    )
    api_url: HttpUrl = Field(
        default=HttpUrl(INORBIT_DEFAULT_API_URL),
    )
    connector_type: str
    connector_config: T
    use_websockets: bool = False
    update_freq: float = 1.0
    location_tz: str = DEFAULT_TIMEZONE
    logging: LoggingConfig = LoggingConfig()
    user_scripts_dir: DirectoryPath | None = None
    inorbit_robot_key: str | None = None
    maps: dict[str, MapConfig] = {}
    env_vars: dict[str, str] = {}
    metrics: MetricsConfig = MetricsConfig()
    fleet: list[RobotConfig]

    def __init__(self, **kwargs):
        # pydantic-settings consumes _env_file before model validators
        # run. Save it in a ContextVar so _instantiate_connector_config
        # can forward it to the nested ConnectorSpecificConfig.
        token = _env_file_var.set(kwargs.get("_env_file", _NOT_SET))
        try:
            super().__init__(**kwargs)
        finally:
            _env_file_var.reset(token)

    @model_validator(mode="before")
    @classmethod
    def _instantiate_connector_config(cls, data):
        """Construct ``connector_config`` via ``__init__`` when it arrives as
        a raw dict so that BaseSettings env-var resolution is triggered."""
        if isinstance(data, dict) and isinstance(data.get("connector_config"), dict):
            ann_type = cls.model_fields["connector_config"].annotation
            if (
                isinstance(ann_type, type)
                and issubclass(ann_type, BaseSettings)
                and ann_type not in (BaseSettings, ConnectorSpecificConfig)
            ):
                env_file_kwargs = {}
                env_file = _env_file_var.get()
                if env_file is not _NOT_SET:
                    env_file_kwargs["_env_file"] = env_file
                data = {
                    **data,
                    "connector_config": ann_type(
                        **data["connector_config"], **env_file_kwargs
                    ),
                }
        return data

    @model_validator(mode="after")
    def _require_api_key_or_robot_key(self) -> Self:
        """Validate that at least one authentication credential is provided.

        Raises:
            ValueError: If neither ``api_key`` nor ``inorbit_robot_key`` is set.

        Returns:
            Self: The validated configuration instance.
        """
        if self.api_key is None and self.inorbit_robot_key is None:
            raise ValueError(
                "At least one of 'api_key' or 'inorbit_robot_key' must be provided"
            )
        return self

    @model_validator(mode="after")
    def _check_connector_type_matches_class_var(self) -> Self:
        """Validate that ``connector_type`` matches the ``CONNECTOR_TYPE`` class
        variable declared by the ``connector_config`` subclass.

        ``CONNECTOR_TYPE`` is the source of truth for the connector's identity
        (declared in code); the ``connector_type`` field on this model is a
        defensive load-time check that the configuration being loaded was
        authored for this connector. The two must agree.

        Raises:
            ValueError: If ``connector_type`` does not equal ``CONNECTOR_TYPE``.

        Returns:
            Self: The validated configuration instance.
        """
        config_cls = type(self.connector_config)
        expected = config_cls.CONNECTOR_TYPE
        if self.connector_type != expected:
            raise ValueError(
                f"connector_type '{self.connector_type}' in configuration does "
                f"not match CONNECTOR_TYPE '{expected}' declared by "
                f"{config_cls.__name__}. The configuration appears to target a "
                "different connector."
            )
        return self

    def to_singular_config(self, robot_id: str) -> Self:
        """Filters out configurations not related to the given robot. The result is a
        config with a fleet field of length 1.

        Args:
            robot_id (str): The ID of the robot to filter the configuration for

        Returns:
            Self: The filtered configuration
        """
        filtered_fleet = [robot for robot in self.fleet if robot.robot_id == robot_id]

        if len(filtered_fleet) != 1:
            raise ValueError(
                f"Expected 1 robot configuration for robot {robot_id}, "
                f"got {len(filtered_fleet)}"
            )

        config = self.__class__(
            **self.model_dump(exclude={"fleet", "connector_config"}),
            connector_config=self.connector_config,
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

    @field_validator("api_key")
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
