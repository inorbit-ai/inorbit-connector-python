import logging
import logging.config
from enum import Enum


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


def setup_logger(log_config_file: str | None, log_level: LogLevels | None):
    """Configures the global logger.

    Args:
        log_config_file (str | None): The path to the logging configuration file.
        log_level (LogLevels | None): The log level to set.
    """
    if log_config_file:
        logging.config.fileConfig(
            log_config_file,
            disable_existing_loggers=False,
        )

    # If a log level is provided, overwrite the log level of the handlers
    # This is useful when a log level is set in the YAML file for an specific robot.
    if log_level:
        for handler in logging.getLogger().handlers:
            handler.setLevel(log_level.value)
