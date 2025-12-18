# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import asyncio
from pathlib import Path

try:
    from typing import override
except ImportError:
    from typing_extensions import override

# InOrbit
from inorbit_connector.connector import CommandResultCode, Connector
from inorbit_connector.models import MapConfigTemp

# Local
from datatypes import ExampleBotConnectorConfig
from robot import Robot, ExampleBotAPIWrapper

# Path to the example map image
EXAMPLE_MAP_PATH = Path(__file__).parent.parent / "example_map.png"

"""
This file holds the main connector class. Overwrite methods as necessary to integrate
the features of your robot into InOrbit.
"""


class ExampleBotConnector(Connector):
    """The example bot connector.

    It inherits from the Connector class and overrides the necessary methods.

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
        self._robot = Robot(
            api_wrapper=ExampleBotAPIWrapper(
                endpoint=config.connector_config.example_bot_custom_value,
                api_key=config.connector_config.example_bot_custom_value,
            ),
            default_update_freq=config.update_freq,
        )

    @override
    async def _connect(self) -> None:
        """Connect to the robot services.

        It starts the API polling loops.
        """
        self._robot.start()

    @override
    async def _disconnect(self) -> None:
        """Disconnect from the robot services."""
        await self._robot.stop()
        self._logger.info(f"Disconnected to robot services at API {self.api_version}")

    @override
    async def _execution_loop(self) -> None:
        """The main execution loop for the connector.

        It gets the last updated data from the state of self._robot and publishes it
        to InOrbit.
        """
        if pose := self._robot.pose:
            self.publish_pose(**pose)
        if odometry := self._robot.odometry:
            self.publish_odometry(**odometry)
        if key_values := self._robot.key_values:
            self.publish_key_values(**key_values)
        if system_stats := self._robot.system_stats:
            self.publish_system_stats(**system_stats)

        self._logger.info("Robot data published")

    @override
    async def _inorbit_command_handler(
        self, command_name: str, args: list, options: dict
    ) -> None:
        """Handle InOrbit commands."""
        self._logger.info(f"Received command: {command_name}")
        self._logger.info(f"Args: {args}")
        self._logger.info(f"Options: {options}")
        self._logger.info("Executing command...")
        await asyncio.sleep(1)
        self._logger.info(f"Command {command_name} executed")
        options["result_function"](CommandResultCode.SUCCESS)

    @override
    async def fetch_map(self, frame_id: str) -> MapConfigTemp | None:
        """Fetch a map when not found in configuration.

        This method is called automatically when publish_pose references a
        frame_id that doesn't have a pre-configured map. Override this to fetch
        maps dynamically from the robot.

        Args:
            frame_id (str): The frame ID of the map to fetch

        Returns:
            MapConfigTemp | None: Map configuration with image bytes, or None
        """
        self._logger.info(f"Fetching map '{frame_id}' from robot")

        # In a real implementation, you would fetch the map from the robot:
        # map_data = await self._robot.get_map(frame_id)

        # For this example, we return the example map for any frame_id
        if EXAMPLE_MAP_PATH.exists():
            return MapConfigTemp(
                image=EXAMPLE_MAP_PATH.read_bytes(),
                map_id=frame_id,
                origin_x=0.0,
                origin_y=0.0,
                resolution=0.05,
            )

        return None
