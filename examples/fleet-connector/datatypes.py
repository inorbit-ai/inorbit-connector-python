# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

from pydantic import BaseModel, field_validator

from inorbit_connector.models import InorbitConnectorConfig


CONNECTOR_TYPE = "example_bot"


class ExampleBotConfig(BaseModel):
    """The configuration for the example bot.

    This is where you would define and validate additional custom fields for the fleet.

    Attributes:
        example_bot_api_version (str): An example field for the API version of the fleet manager
        example_bot_hw_rev (str): An example field for the HW revision of the fleet
        example_bot_custom_value (str): An example field for a custom value of the fleet
    """

    example_bot_api_version: str
    example_bot_hw_rev: str
    example_bot_custom_value: str


class ExampleBotConnectorConfig(InorbitConnectorConfig):
    """The configuration for the example bot fleet connector.

    Each connector should create a class that inherits from InorbitConnectorConfig.

    Attributes:
        connector_config (ExampleBotConfig): The config with custom fields for the fleet
    """

    connector_config: ExampleBotConfig

    # noinspection PyMethodParameters
    @field_validator("connector_type")
    def check_connector_type(cls, connector_type: str) -> str:
        """Validate the connector type.

        This should always be equal to the pre-defined constant.

        Args:
            connector_type (str): The defined connector type passed in

        Returns:
            str: The validated connector type

        Raises:
            ValueError: If the connector type is not equal to the pre-defined constant
        """
        if connector_type != CONNECTOR_TYPE:
            raise ValueError(
                f"Expected connector type '{CONNECTOR_TYPE}' not '{connector_type}'"
            )
        return connector_type
