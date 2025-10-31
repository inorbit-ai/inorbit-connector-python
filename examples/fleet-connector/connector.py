# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import asyncio

try:
    from typing import override
except ImportError:
    from typing_extensions import override

# InOrbit
from inorbit_connector.connector import CommandResultCode, FleetConnector

# Local
from datatypes import ExampleBotConnectorConfig
from fleet_client import FleetManager, FleetManagerAPIWrapper

"""
This file holds the main fleet connector class. It demonstrates how to use
the FleetConnector base class to manage multiple robots that share the same
fleet manager API.
"""


class ExampleBotFleetConnector(FleetConnector):
    """The example bot fleet connector.

    It inherits from the FleetConnector class and overrides the necessary methods.
    This connector manages multiple robots by polling a fleet manager API.

    Args:
        robot_ids (list[str]): List of robot IDs in the fleet
        config (ExampleBotConnectorConfig): The configuration for the connector
    """

    def __init__(self, config: ExampleBotConnectorConfig) -> None:
        super().__init__(config)

        # Setup any other initialization things here
        self.api_version = config.connector_config.example_bot_api_version
        self.hw_rev = config.connector_config.example_bot_hw_rev
        self.custom_value = config.connector_config.example_bot_custom_value

        # Initialize the fleet manager abstraction
        # This simulates a fleet manager API that provides data for all robots
        self._fleet_manager = FleetManager(
            robot_ids=self.robot_ids,
            api_wrapper=FleetManagerAPIWrapper(
                endpoint=config.connector_config.example_bot_custom_value,
                api_key=config.connector_config.example_bot_custom_value,
            ),
            default_update_freq=config.update_freq,
        )

    @override
    async def _connect(self) -> None:
        """Connect to the fleet manager services.

        This starts the API polling loops that fetch data for all robots.
        """
        self._fleet_manager.start()

        # Here the connector may fetch a robot list from the fleet manager. e.g.:
        # robots: list[RobotConfig] = self._fleet_manager.fetch_robot_list()
        # self.update_fleet(robots)
        # `robots` will be added to the InOrbit fleet

        self._logger.info(
            f"Connected to fleet manager API {self.api_version} for {len(self.robot_ids)} "
            f"robots: {self.robot_ids}"
        )

    @override
    async def _disconnect(self) -> None:
        """Disconnect from the fleet manager services."""
        await self._fleet_manager.stop()
        self._logger.info(
            f"Disconnected from fleet manager services at API {self.api_version}"
        )

    @override
    async def _execution_loop(self) -> None:
        """The main execution loop for the fleet connector.

        This gets the latest data from the fleet manager and publishes it to InOrbit
        for each robot. The key difference from single robot connectors is that we
        iterate over all robot_ids and publish data for each one.
        """
        published_count = 0

        for robot_id in self.robot_ids:
            # Publish pose if available
            if pose := self._fleet_manager.get_robot_pose(robot_id):
                self.publish_robot_pose(robot_id, **pose)
                published_count += 1

            # Publish odometry if available
            if odometry := self._fleet_manager.get_robot_odometry(robot_id):
                self.publish_robot_odometry(robot_id, **odometry)

            # Publish key values if available
            if key_values := self._fleet_manager.get_robot_key_values(robot_id):
                self.publish_robot_key_values(robot_id, **key_values)

            # Publish system stats if available
            if system_stats := self._fleet_manager.get_robot_system_stats(robot_id):
                self.publish_robot_system_stats(robot_id, **system_stats)

        if published_count > 0:
            self._logger.info(f"Published data for {published_count} robots in fleet")

    @override
    async def _inorbit_robot_command_handler(
        self, robot_id: str, command_name: str, args: list, options: dict
    ) -> None:
        """Handle InOrbit commands for a specific robot in the fleet.

        This method is called when a command is received from InOrbit for a specific
        robot in the fleet. You would typically forward the command to the fleet
        manager API or execute it directly on the robot.
        """
        self._logger.info(f"Received command '{command_name}' for robot '{robot_id}'")
        self._logger.info(f"Args: {args}")
        self._logger.info(f"Options: {options}")
        self._logger.info(f"Executing command for robot {robot_id}...")

        # Simulate command execution
        # In a real implementation, you would send this command to the fleet manager
        # or directly to the robot
        await asyncio.sleep(1)

        self._logger.info(
            f"Command '{command_name}' executed successfully for robot '{robot_id}'"
        )
        options["result_function"](CommandResultCode.SUCCESS)

    def _is_fleet_robot_online(self, robot_id: str) -> bool:
        """Check if a specific robot in the fleet is online.

        This method can be overridden to provide robot-specific health checks.
        For example, you could check if the robot has recently sent data or
        query the fleet manager API for the robot's status.

        Args:
            robot_id (str): The robot ID to check

        Returns:
            bool: True if robot is online, False otherwise
        """
        # In a real implementation, you would check the actual robot status
        # For this example, we'll check if we have recent data for the robot
        key_values = self._fleet_manager.get_robot_key_values(robot_id)
        if key_values:
            # Consider robot online if it's not in error state
            return key_values.get("status") != "error"

        # Default to True if we don't have status data yet
        return True
