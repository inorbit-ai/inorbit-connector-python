#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import logging
import os
import random

# Third-party
from pydantic import field_validator, BaseModel

# InOrbit
from inorbit_connector.connector import Connector
from inorbit_connector.models import InorbitConnectorConfig
from inorbit_connector.utils import read_yaml

CONFIG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "example.yaml")
ROBOT_ID = "my-example-robot"
CONNECTOR_TYPE = "example_bot"


class ExampleBotConfig(BaseModel):
    """The configuration for the example bot.

    This is where you would define and validate additional custom fields for the robot.

    Attributes:
        example_bot_api_version (str): An example field for the API version of the robot
        example_bot_hw_rev (str): An example field for the HW revision of the robot
        example_bot_custom_value (str): An example field for a custom value of the robot
    """

    example_bot_api_version: str
    example_bot_hw_rev: str
    example_bot_custom_value: str


class ExampleBotConnectorConfig(InorbitConnectorConfig):
    """The configuration for the example bot connector.

    Each connector should create a class that inherits from InorbitConnectorConfig.

    Attributes:
        connector_config (ExampleBotConfig): The config with custom fields for the robot
    """

    connector_config: ExampleBotConfig

    # noinspection PyMethodParameters
    @field_validator("connector_type")
    def check_whitespace(cls, connector_type: str) -> str:
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


class ExampleBotConnector(Connector):
    """The example bot connector.

    This is the brains of the connector. Overwrite methods as necessary to integrate
    the features of your robot into InOrbit.

    Args:
            robot_id (str): The ID of the InOrbit robot
            config (ExampleBotConnectorConfig): The configuration for the connector
    """

    def __init__(self, robot_id: str, config: ExampleBotConnectorConfig) -> None:
        super().__init__(robot_id, config)

        # Setup any other initialization things here
        self.api_version = config.connector_config.example_bot_api_version
        self.hw_rev = config.connector_config.example_bot_hw_rev
        self.custom_value = config.connector_config.example_bot_custom_value

    def _connect(self) -> None:
        """Connect to the robot services.

        This method should always call super.
        """
        super()._connect()
        # Do some magic here...
        self._logger.info(f"Connected to robot services at API {self.api_version}")

    def _disconnect(self) -> None:
        """Disconnect from the robot services.

        This method should always call super.
        """
        super()._disconnect()
        # Do some magic here...
        self._logger.info(f"Disconnected to robot services at API {self.api_version}")

    def _execution_loop(self) -> None:
        """The main execution loop for the connector.

        This is where the meat of your connector is implemented. It is good practice to
        handle things like action requests in a threaded manner so that the connector
        does not block the execution loop.
        """
        # Do some magic here...

        # Some examples...

        # Publish key-values...
        key_values = self.config.connector_config.model_dump()
        self._robot_session.publish_key_values(key_values)

        # Publish system stats...
        cpu = random.uniform(0.1, 0.9)
        ram = random.uniform(0.2, 0.8)
        hdd = random.uniform(0.3, 0.7)
        self._robot_session.publish_system_stats(cpu, ram, hdd)

        # Publish pose...
        x = random.uniform(-1.0, 1.0)
        y = random.uniform(-1.0, 1.0)
        yaw = random.uniform(-3.14, 3.14)
        # Note that if the frame_id is present in the maps definition,
        # the map image will be automatically uploaded to InOrbit.
        frame_id = "frameIdA"
        self.publish_pose(x, y, yaw, frame_id)


def main():
    # Setup the logger
    logger = logging.getLogger("main")
    logging.basicConfig(level=logging.INFO)

    try:
        # Parse the YAML
        yaml = read_yaml(CONFIG_FILE, ROBOT_ID)
        config = ExampleBotConnectorConfig(**yaml)
    except FileNotFoundError:
        logger.error(f"'{CONFIG_FILE}' configuration file does not exist")
        exit(1)
    except IndexError:
        logger.error(f"'{ROBOT_ID}' not found in '{CONFIG_FILE}'")
        exit(1)
    except ValueError as e:
        logger.error(e)
        exit(1)

    logger.info(
        f"Configuration loaded and validated for {ROBOT_ID}\n"
        f"\tconnector_config: {config.connector_config.model_dump_json()}"
    )

    logger.info("Starting connector...")
    connector = ExampleBotConnector(ROBOT_ID, config)
    connector.start()

    try:
        connector.join()
    except KeyboardInterrupt:
        logger.info("...exiting")
        connector.stop()


if __name__ == "__main__":
    main()
