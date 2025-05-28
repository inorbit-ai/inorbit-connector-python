#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import os
import warnings
from typing import List

# Third-party
import pytz
from inorbit_edge.models import CameraConfig
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
from pydantic import (
    BaseModel,
    field_validator,
    HttpUrl,
    FilePath,
    DirectoryPath,
    Field,
    model_validator,
)

# InOrbit
from inorbit_connector.utils import DEFAULT_TIMEZONE, DEFAULT_LOGGING_CONFIG
from inorbit_connector.logging.logger import LogLevels

# Ensure deprecation warnings are shown
warnings.filterwarnings("always", category=DeprecationWarning)


class MapConfig(BaseModel):
    """Class representing a map configuration.

    Attributes:
        file (FilePath): The path to the PNG map file
        map_id (str): The map id
        origin_x (float): The x origin of the map
        origin_y (float): The y origin of the map
        resolution (float): The resolution
    """

    file: FilePath
    map_id: str
    origin_x: float
    origin_y: float
    resolution: float

    # noinspection PyMethodParameters
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
        if not file.suffix.lower() == ".png":
            raise ValueError("The map file must be a PNG file")
        return file


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


class InorbitConnectorConfig(BaseModel):
    """Class representing an Inorbit connector model.

    This should not be instantiated on its own.

    A Connector specific configuration should be defined in a subclass adding the
    "connector_config" field.

    The following environment variables will be read during instantiation:

    * INORBIT_API_KEY (required): The InOrbit API key
    * INORBIT_API_URL: The URL of the API endpoint or inorbit_edge's
                       INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL by default

    Attributes:
        api_key (str | None, optional): The InOrbit API key
        api_url (HttpUrl, optional): The URL of the API or inorbit_edge's
                                     INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL by default
        cameras (List[CameraConfig], optional): The list of cameras
        connector_type (str): The type of connector (see Class comment above)
        connector_config (BaseModel): The configuration for the connector
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
        environment (dict[str, str], optional): Environment variables to be set in the
            connector or user scripts. The key is the environment variable name and the
            value is the value to set.
    """

    api_key: str | None = os.getenv("INORBIT_API_KEY")
    api_url: HttpUrl = os.getenv("INORBIT_API_URL", INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL)
    cameras: List[CameraConfig] = []
    connector_type: str
    connector_config: BaseModel
    update_freq: float = 5.0
    location_tz: str = DEFAULT_TIMEZONE
    logging: LoggingConfig = LoggingConfig()
    user_scripts_dir: DirectoryPath | None = None
    account_id: str | None = None
    inorbit_robot_key: str | None = None
    maps: dict[str, MapConfig] = {}
    env_vars: dict[str, str] = {}
    # Kept for backwards compatibility
    log_level: LogLevels | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def warn_log_level_deprecated(self) -> "InorbitConnectorConfig":
        """Warn if log_level is set as it is deprecated.

        Returns:
            InorbitConnectorConfig: The model instance
        """
        if self.log_level is not None:
            warnings.warn(
                "The 'log_level' field is deprecated. "
                "Please use 'logging.log_level' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if self.logging.log_level is None:
                self.logging.log_level = self.log_level
        return self

    # noinspection PyMethodParameters
    @field_validator("api_key", "account_id")
    def check_whitespace(cls, value: str) -> str:
        """Check if the api_key contains whitespace.

        This is used for the api_key.

        Args:
            value (str): The api_key to be checked

        Raises:
            ValueError: If the api_key contains whitespace

        Returns:
            str: The given value if it does not contain whitespaces
        """
        if any(char.isspace() for char in value):
            raise ValueError("Whitespaces are not allowed")
        return value

    # noinspection PyMethodParameters
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

    # noinspection PyMethodParameters
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
