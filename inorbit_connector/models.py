#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import os
from pathlib import Path
from typing import List

# Third-party
import pytz
from inorbit_edge.models import CameraConfig
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
from pydantic import BaseModel, field_validator, HttpUrl

# InOrbit
from inorbit_connector.utils import LogLevels, DEFAULT_TIMEZONE


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
        log_level (LogLevels, optional): The log level or LogLevels.INFO by default
        user_scripts_dir (Path | None, optional): The location of custom user scripts
    """

    api_key: str | None = os.getenv("INORBIT_API_KEY")
    api_url: HttpUrl = os.getenv("INORBIT_API_URL", INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL)
    cameras: List[CameraConfig] = []
    connector_type: str
    connector_config: BaseModel
    update_freq: float = 5.0
    location_tz: str = DEFAULT_TIMEZONE
    log_level: LogLevels = LogLevels.INFO
    user_scripts_dir: Path | None = None

    # noinspection PyMethodParameters
    @field_validator("api_key")
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

    # noinspection PyMethodParameters
    @field_validator("user_scripts_dir")
    def is_directory(cls, user_scripts_dir: Path | None) -> Path | None:
        """Check if an argument is a valid path.

        This is used for the user_scripts_dir value.

        Args:
            user_scripts_dir (Path | None): The path to check or None

        Raises:
            ValueError: If the path is not valid

        Returns:
            (Path | None): The valid path or None if optional
        """
        if user_scripts_dir and not user_scripts_dir.is_dir():
            raise ValueError("Must be a valid directory")
        return user_scripts_dir
