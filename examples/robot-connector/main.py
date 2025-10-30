# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

import argparse
import logging
import signal
import sys

from inorbit_connector.utils import read_yaml
from connector import ExampleBotConnector
from datatypes import ExampleBotConnectorConfig

"""
This is the main entry point for the connector.
It parses arguments, processes the configuration file and starts the connector.
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
    """Parses arguments, processes the configuration file and starts the connector."""
    parser = CustomParser(prog="sample_connector")
    parser.add_argument(
        "-c",
        "--config",
        default="example.yaml",
        type=str,
        required=True,
        help="Path to the YAML file containing the robot configuration",
    )
    parser.add_argument(
        "-id",
        "--robot_id",
        type=str,
        required=True,
        help="InOrbit robot id. Will be searched in the config file",
    )

    args = parser.parse_args()
    robot_id, config_filename = args.robot_id, args.config

    try:
        yaml_data = read_yaml(config_filename)
        config = ExampleBotConnectorConfig(**yaml_data)
    except FileNotFoundError:
        LOGGER.error(f"Configuration file '{config_filename}' not found")
        exit(1)
    except ValueError as e:
        LOGGER.error(f"Configuration validation error: {e}")
        exit(1)
    connector = ExampleBotConnector(robot_id, config)
    LOGGER.info("Starting connector...")
    connector.start()

    # Register a signal handler for graceful shutdown
    # When a keyboard interrupt is received (Ctrl+C), the connector will be stopped
    signal.signal(signal.SIGINT, lambda sig, frame: connector.stop())

    # Wait for the connector to finish
    connector.join()


if __name__ == "__main__":
    start()
