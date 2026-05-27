# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

from inorbit_connector.models import ConnectorSpecificConfig


class ExampleBotConfig(ConnectorSpecificConfig):
    """The configuration for the example bot.

    This is where you would define and validate additional custom fields for the robot.

    Attributes:
        example_bot_api_version (str): An example field for the API version of the robot
        example_bot_hw_rev (str): An example field for the HW revision of the robot
        example_bot_custom_value (str): An example field for a custom value of the robot
    """

    CONNECTOR_TYPE = "example_bot"

    example_bot_api_version: str
    example_bot_hw_rev: str
    example_bot_custom_value: str
