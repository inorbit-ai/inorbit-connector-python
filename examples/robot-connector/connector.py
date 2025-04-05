# Standard
import asyncio

# InOrbit
from inorbit_connector.connector import Connector

# Local
from datatypes import ExampleBotConnectorConfig
from robot import Robot, ExampleBotAPIWrapper

"""
This file holds the main connector class. Overwrite methods as necessary to integrate
the features of your robot into InOrbit.
"""


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

        # Initialize the robot abstraction
        self._stop_event = asyncio.Event()
        self._robot = Robot(
            api_wrapper=ExampleBotAPIWrapper(
                endpoint=config.connector_config.example_bot_custom_value,
                api_key=config.connector_config.example_bot_custom_value,
            ),
            stop_event=self._stop_event,
            default_update_freq=config.update_freq,
        )

    async def _connect(self) -> None:
        """Connect to the robot services.

        It starts the API polling loops.
        """
        self._robot.start()

    async def _disconnect(self) -> None:
        """Disconnect from the robot services."""
        await self._robot.stop()
        self._logger.info(f"Disconnected to robot services at API {self.api_version}")

    async def _execution_loop(self) -> None:
        """The main execution loop for the connector.

        It gets the last updated data from the state of self._robot and publishes it
        to InOrbit.
        """
        if pose := self._robot.pose:
            self._robot_session.publish_pose(**pose)
        if odometry := self._robot.odometry:
            self._robot_session.publish_odometry(**odometry)
        if key_values := self._robot.key_values:
            self._robot_session.publish_key_values(**key_values)
        if system_stats := self._robot.system_stats:
            self._robot_session.publish_system_stats(**system_stats)

        self._logger.info("Robot data published")

    async def _inorbit_command_handler(
        self, command_name: str, args: list, options: dict
    ) -> None:
        """Handle InOrbit commands."""
        self._logger.info(f"Received command: {command_name}")
        self._logger.info(f"Args: {args}")
        self._logger.info(f"Options: {options}")
        self._logger.info("Executing command...")
        asyncio.sleep(1)
        self._logger.info(f"Command {command_name} executed")
