# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

import argparse
import logging
import signal
import sys

from inorbit_connector.utils import read_yaml
from connector import ExampleBotFleetConnector
from datatypes import ExampleBotConnectorConfig

"""
This is the main entry point for the fleet connector.
It parses arguments, processes the configuration file and starts the fleet connector.
"""

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


class CustomParser(argparse.ArgumentParser):
    # Handles missing parameters by printing the help message
    def error(self, message):
        sys.stderr.write("error: %s\n" % message)
        self.print_help()
        sys.exit(2)


def start():
    """Parses arguments, processes the configuration file and starts the fleet connector."""
    parser = CustomParser(prog="fleet_connector")
    parser.add_argument(
        "-c",
        "--config",
        default="example.fleet.yaml",
        type=str,
        required=True,
        help="Path to the YAML file containing the fleet configuration",
    )

    args = parser.parse_args()
    config_filename = args.config

    try:
        # Read the fleet configuration file
        yaml_data = read_yaml(config_filename)

        # Create the connector configuration
        config = ExampleBotConnectorConfig(**yaml_data)

        # Extract robot IDs from the fleet configuration for logging purposes
        robot_ids = [robot.robot_id for robot in config.fleet]

        LOGGER.info(f"Configuration loaded for fleet of {len(robot_ids)} robots")
        LOGGER.info(f"Robot IDs: {robot_ids}")
        LOGGER.info(f"Connector config: {config.connector_config.model_dump_json()}")

    except FileNotFoundError:
        LOGGER.error(f"Configuration file '{config_filename}' not found")
        exit(1)
    except ValueError as e:
        LOGGER.error(f"Configuration validation error: {e}")
        exit(1)

    # Create and start the fleet connector
    connector = ExampleBotFleetConnector(config)
    LOGGER.info("Starting fleet connector...")
    connector.start()

    # Register a signal handler for graceful shutdown
    # When a keyboard interrupt is received (Ctrl+C), the connector will be stopped
    signal.signal(signal.SIGINT, lambda sig, frame: connector.stop())

    # Wait for the connector to finish
    connector.join()


if __name__ == "__main__":
    start()
