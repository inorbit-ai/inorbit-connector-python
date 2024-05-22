#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import os
from typing import List

# Third Party
import pytz
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
from pydantic import BaseModel, HttpUrl, field_validator, AnyUrl

# Local
from inorbit_connector.config import DEFAULT_TIMEZONE
from inorbit_connector.utils import LogLevels


class CameraModel(BaseModel):
    """A class representing a camera configuration model.

    This class inherits from the `BaseModel` class. None values should be interpreted as
    "use the default values".

    Attributes:
        video_url (AnyUrl): The URL of the video feed from the camera
        rate (int, optional): The rate at which frames are captured from the camera
        quality (int, optional): The quality of the captured frames from the camera
        scaling (float, optional): The scaling factor for the captured frames
    """
    # TODO(russell): Needs a custom decoder to handle the AnyUrl type.
    video_url: AnyUrl
    quality: int = None
    rate: int = None
    scaling: float = None

    # noinspection PyMethodParameters
    @field_validator("quality")
    def check_quality_range(cls, quality: int | None) -> int | None:
        """Check if the quality is between 1 and 100.

        Args:
            quality (int | None): The quality value to be checked
        Raises:
            ValueError: If the value is not between 1 and 100
        Returns:
            int | None: The given value if it is between 1 and 100
        """
        if quality is not None and not (1 <= quality <= 100):
            raise ValueError("Must be between 1 and 100")
        return quality

    # noinspection PyMethodParameters
    @field_validator("rate", "scaling", "connector_update_freq")
    def check_positive(cls, value: float | None) -> float | None:
        """Check if an argument is positive and non-zero.

        This is used for rate and scaling values.

        Args:
            value (float | None): The value to be checked.
        Raises:
            ValueError: If the value is less than or equal to zero.
        Returns:
            float | None : The given value if it is positive and non-zero, or None if
                           input value was None.
        """
        if value is not None and value <= 0:
            raise ValueError("Must be positive and non-zero")
        return value


class InorbitConnectorModel(BaseModel):
    """Class representing an Inorbit connector model.

    This should not be instantiated. Connector specific configuration should be defined
    in a subclass adding the "connector_config" field.

    Attributes:
        api_token (str): The inOrbit API token.
        api_url (HttpUrl, optional): The URL of the API. Defaults to inorbit_edge's
                                     INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
        cameras (List[CameraModel] | None, optional): The list of cameras (or None).
        connector_type (str): The type of connector.
        connector_config (BaseModel): The configuration for the connector.
        connector_update_freq (float, optional): Update frequency in Hz (default = 1)
        location_tz (str, optional): The timezone of the location. Defaults to "UTC".
        log_level (LogLevels, optional): The log level. Defaults to LogLevels.INFO.
        user_scripts_dir (str, optional): The location of customer user scripts.
    """
    api_token: str = os.getenv("INORBIT_API_TOKEN")
    api_url: HttpUrl = os.getenv("INORBIT_API_URL", INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL)
    cameras: List[CameraModel] = []
    connector_type: str
    connector_config: BaseModel
    connector_update_freq: float = 1.0
    location_tz: str = DEFAULT_TIMEZONE
    log_level: LogLevels = LogLevels.INFO
    user_scripts_dir: str = "./user_scripts"

    # noinspection PyMethodParameters
    @field_validator("api_token")
    def check_whitespace(cls, value: str) -> str:
        """Check if the api_token contains whitespace.

        This is used for the api_token.

        Args:
            value (str): The api_token to be checked.

        Raises:
            ValueError: If the api_token contains whitespace.

        Returns:
            str: The given value if it does not contain whitespace.
        """
        if any(char.isspace() for char in value):
            raise ValueError("Whitespace is not allowed in the api_token")
        return value

    # noinspection PyMethodParameters
    @field_validator("connector_config")
    def connector_config_check(cls, connector_config: BaseModel) -> BaseModel:
        """
        Validate the configuration is not just the BaseModel.

        This will prevent the class from being instantiated if the configuration is
        just the BaseModel.

        Args:
            connector_config (BaseModel): The configuration for the connector.

        Returns:
            BaseModel: The validated configuration for the connector.

        Raises:
            ValueError: If the configuration is just the BaseModel.
        """
        if connector_config.__class__ == BaseModel:
            raise ValueError("No subclass of BaseModel found")
        return connector_config

    # noinspection PyMethodParameters
    @field_validator("location_tz")
    def location_tz_must_exist(cls, location_tz: str) -> str:
        """Validate the timezone exists in the pytz package.

        This will prevent the class from being instantiated if location_tz is not found
        in the pytz package.

        Args:
            location_tz (str): A string representing the timezone location.
        Returns:
            str: A string representing the validated timezone location.
        Raises:
            ValueError: If the provided timezone location is not a valid pytz timezone.
        """
        if location_tz not in pytz.all_timezones:
            raise ValueError("Timezone must be a valid pytz timezone")
        return location_tz
