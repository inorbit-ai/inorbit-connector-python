# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

import argparse
import logging
import signal
import sys

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

    # TODO: Update configuration management utilities to support fleet configurations
    try:
        # Read the fleet configuration file
        import yaml

        with open(config_filename, "r") as f:
            yaml_data = yaml.safe_load(f)

        # Extract the common configuration and robot IDs
        if "common" not in yaml_data:
            LOGGER.error("'common' section not found in configuration file")
            exit(1)

        if "robots" not in yaml_data:
            LOGGER.error("'robots' section not found in configuration file")
            exit(1)

        common_config = yaml_data["common"]
        robot_ids = yaml_data["robots"]

        if not isinstance(robot_ids, list) or len(robot_ids) == 0:
            LOGGER.error("'robots' must be a non-empty list of robot IDs")
            exit(1)

        # Create the connector configuration from the common section
        config = ExampleBotConnectorConfig(**common_config)

        LOGGER.info(f"Configuration loaded for fleet of {len(robot_ids)} robots")
        LOGGER.info(f"Robot IDs: {robot_ids}")
        LOGGER.info(f"Connector config: {config.connector_config.model_dump_json()}")

    except FileNotFoundError:
        LOGGER.error(f"Configuration file '{config_filename}' not found")
        exit(1)
    except yaml.YAMLError as e:
        LOGGER.error(f"Error parsing YAML file: {e}")
        exit(1)
    except ValueError as e:
        LOGGER.error(f"Configuration validation error: {e}")
        exit(1)

    # Create and start the fleet connector
    connector = ExampleBotFleetConnector(robot_ids, config)
    LOGGER.info("Starting fleet connector...")
    connector.start()

    # Register a signal handler for graceful shutdown
    # When a keyboard interrupt is received (Ctrl+C), the connector will be stopped
    signal.signal(signal.SIGINT, lambda sig, frame: connector.stop())

    # Wait for the connector to finish
    connector.join()


if __name__ == "__main__":
    start()
