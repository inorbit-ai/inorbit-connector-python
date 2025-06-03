# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2025 InOrbit, Inc.

# Standard
import logging
import logging.config
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inorbit_connector.models import LoggingConfig


class LogLevels(str, Enum):
    """An enumeration class representing different levels of log messages.

    Log levels for logging.

    See https://docs.python.org/3/library/logging.html#logging-levels

    Attributes:
        DEBUG: Represents the debug log level
        INFO: Represents the info log level
        WARNING: Represents the warning log level
        ERROR: Represents the error log level
        CRITICAL: Represents the critical log level
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def setup_logger(config: "LoggingConfig"):
    """Configures the global logger.

    Args:
        config (LoggingConfig): The logging configuration.
    """
    if config.config_file:
        logging.config.fileConfig(
            config.config_file,
            disable_existing_loggers=False,
            defaults=config.defaults,
        )

    # If a log level is provided, overwrite root logger level
    # This is useful when a log level is set in the YAML file for an specific robot.
    if config.log_level:
        root_logger = logging.getLogger()
        root_logger.setLevel(config.log_level.value)
