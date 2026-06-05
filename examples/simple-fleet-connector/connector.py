#!/usr/bin/env python

# Copyright 2025 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import asyncio
import logging
import random
import signal
from pathlib import Path

try:
    from typing import override
except ImportError:
    from typing_extensions import override

# InOrbit
from inorbit_connector.commands import CommandResultCode
from inorbit_connector.connector import FleetConnector
from inorbit_connector.models import ConnectorRootConfig, ConnectorSpecificConfig
from inorbit_connector.utils import read_yaml

CONFIG_FILE = (
    Path(__file__).resolve().parent.parent / "example.fleet.yaml"
)  # ../example.fleet.yaml


class ExampleBotConfig(ConnectorSpecificConfig):
    """The configuration for the example bot.

    This is where you would define and validate additional custom fields for the fleet.

    Attributes:
        example_bot_api_version (str): API version of the fleet manager
        example_bot_hw_rev (str): An example field for the HW revision of the fleet
        example_bot_custom_value (str): An example field for a custom value of the fleet
    """

    CONNECTOR_TYPE = "example_bot"

    example_bot_api_version: str
    example_bot_hw_rev: str
    example_bot_custom_value: str


async def get_fleet_robot_data(robot_id: str) -> dict:
    """Simulate a request to the fleet manager's API for a specific robot."""
    await asyncio.sleep(random.uniform(0.1, 0.3))

    # Simulate different robot behaviors based on robot_id
    robot_index = int(robot_id.split("-")[-1])  # Extract number from robot ID

    return {
        "linear_speed": random.uniform(0.1, 0.9) + (robot_index * 0.1),
        "angular_speed": random.uniform(0.1, 0.9) + (robot_index * 0.05),
        "pose": {
            "x": random.uniform(-1.0, 1.0) + (robot_index * 2.0),
            "y": random.uniform(-1.0, 1.0) + (robot_index * 2.0),
            "yaw": random.uniform(-3.14, 3.14),
            "frame_id": "frameIdA",
        },
        "system_stats": {
            "cpu_load_percentage": random.uniform(0.1, 0.9),
            "ram_usage_percentage": random.uniform(0.2, 0.8),
            "hdd_usage_percentage": random.uniform(0.3, 0.7),
        },
        "robot_status": {
            "status": "running",
            "error": None,
            "message": f"Robot {robot_id} is executing mission {robot_index}",
            "battery_level": random.uniform(0.2, 1.0),
        },
    }


class ExampleBotFleetConnector(FleetConnector):
    """The example bot fleet connector.

    Demonstrates how to manage a fleet of robots using the
    FleetConnector base class. Simulates fetching data from a fleet
    manager API and publishing data for multiple robots.

    Args:
        robot_ids (list[str]): List of robot IDs in the fleet
        config (ConnectorRootConfig[ExampleBotConfig]):
            The configuration for the connector
    """

    def __init__(self, config: ConnectorRootConfig[ExampleBotConfig]) -> None:
        super().__init__(config)

        # Setup any other initialization things here
        self.api_version = config.connector_config.example_bot_api_version
        self.hw_rev = config.connector_config.example_bot_hw_rev
        self.custom_value = config.connector_config.example_bot_custom_value

        # Testing the logger
        self._logger.debug("This is a debug message 🐛")
        self._logger.info("This is an info message ℹ️")
        self._logger.warning("This is a warning message ⚠️")
        self._logger.error("This is an error message ❌")
        self._logger.critical("This is a critical message 💥")

    @override
    async def _connect(self) -> None:
        """Connect to the fleet manager services."""
        self._logger.info(
            f"Connected to fleet manager services at API {self.api_version}"
        )
        self._logger.info(
            f"Managing fleet of {len(self.robot_ids)} robots: {self.robot_ids}"
        )

    @override
    async def _disconnect(self) -> None:
        """Disconnect from the fleet manager services."""
        self._logger.info(
            f"Disconnected from fleet manager services at API {self.api_version}"
        )

    @override
    async def _execution_loop(self) -> None:
        """The main execution loop for the fleet connector.

        Fetches data for multiple robots and publishes to InOrbit.
        Unlike single robot connectors, we specify robot_id for each
        publishing operation.
        """

        # Snapshot the fleet once: robot_ids may change at runtime where runtime fleet
        # updates are implemented, so reading it once ensures consistency.
        robot_ids = self.robot_ids

        # Fetch data for all robots concurrently
        robot_data_tasks = [get_fleet_robot_data(robot_id) for robot_id in robot_ids]
        robot_data_list = await asyncio.gather(*robot_data_tasks)

        # Create a mapping of robot_id to data
        robot_data_map = dict(zip(robot_ids, robot_data_list))

        # Publish data for each robot
        for robot_id, data in robot_data_map.items():
            # Publish key-values (robot-specific configuration)
            key_values = {
                "fleet_api_version": self.api_version,
                "fleet_hw_rev": self.hw_rev,
                "fleet_custom_value": self.custom_value,
                **data["robot_status"],
            }
            self.publish_robot_key_values(robot_id, **key_values)

            # Publish system stats
            self.publish_robot_system_stats(robot_id, **data["system_stats"])

            # Publish pose
            pose = data["pose"]
            self.publish_robot_pose(
                robot_id, pose["x"], pose["y"], pose["yaw"], pose["frame_id"]
            )

            # Publish odometry
            odometry = {
                "linear_speed": data["linear_speed"],
                "angular_speed": data["angular_speed"],
            }
            self.publish_robot_odometry(robot_id, **odometry)

        self._logger.info(
            f"Fleet data updated and published for {len(robot_ids)} robots"
        )

    @override
    async def _inorbit_robot_command_handler(
        self, robot_id: str, command_name: str, args: list, options: dict
    ) -> None:
        """Handle InOrbit commands for a specific robot in the fleet."""
        self._logger.info(f"Received command '{command_name}' for robot '{robot_id}'")
        self._logger.info(f"Args: {args}")
        self._logger.info(f"Options: {options}")
        self._logger.info(f"Executing command for robot {robot_id}...")

        # Simulate command execution time
        await asyncio.sleep(1)

        self._logger.info(
            f"Command '{command_name}' executed successfully for robot '{robot_id}'"
        )
        options["result_function"](CommandResultCode.SUCCESS)

    def _is_fleet_robot_online(self, robot_id: str) -> bool:
        """Check if a specific robot in the fleet is online.

        This method can be overridden to provide robot-specific health checks.
        For this example, we'll simulate all robots being online.

        Args:
            robot_id (str): The robot ID to check

        Returns:
            bool: True if robot is online, False otherwise
        """
        # In a real implementation, this would check the actual robot status
        # For this example, we'll simulate all robots being online
        return True


def main():
    """Main entry point for the fleet connector example."""
    # Setup the logger
    logger = logging.getLogger("main")
    logging.basicConfig(level=logging.INFO)

    try:
        # Read the YAML configuration
        yaml_data = read_yaml(CONFIG_FILE)

        # Create the connector configuration
        config = ConnectorRootConfig[ExampleBotConfig](**yaml_data)

        # Extract robot IDs from the fleet configuration for logging purposes
        robot_ids = [robot.robot_id for robot in config.fleet]

    except FileNotFoundError:
        logger.error(f"'{CONFIG_FILE}' configuration file does not exist")
        exit(1)
    except ValueError as e:
        logger.error(f"Configuration validation error: {e}")
        exit(1)

    logger.info(
        f"Configuration loaded and validated for fleet\n"
        f"\tRobot IDs: {robot_ids}\n"
        f"\tconnector_config: {config.connector_config.model_dump_json()}"
    )

    logger.info("Starting fleet connector...")
    connector = ExampleBotFleetConnector(config)
    connector.start()

    # Register a signal handler for graceful shutdown
    # When a keyboard interrupt is received (Ctrl+C), the connector will be stopped
    signal.signal(signal.SIGINT, lambda sig, frame: connector.stop())

    # Wait for the connector to finish
    connector.join()


if __name__ == "__main__":
    main()
