---
title: "Logging"
description: "Logging configuration specification"
---

This page specifies logging-related helpers from `inorbit_connector.logging`.

(spec-logging-setup-logger)=
## `setup_logger(config: LoggingConfig) -> None`

Configures Python logging using the standard library `logging.config.fileConfig`.

Behavior:

- If `config.config_file` is set, it is loaded via `logging.config.fileConfig(..., disable_existing_loggers=False, defaults=config.defaults)`.
- If `config.log_level` is set, the root logger level is overridden to that value after loading the config file.

(spec-logging-loggingconfig)=
## `LoggingConfig` / `LogLevels`

- `LoggingConfig` is the configuration model used by `setup_logger()`.
- `LogLevels` is an enum of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

(spec-logging-conditional-colored-formatter)=
## `ConditionalColoredFormatter`

Formatter used by the package default logging configuration.

Behavior:

- If `colorlog` is installed, it uses `colorlog.ColoredFormatter`.
- Otherwise it falls back to `logging.Formatter` and removes `%(log_color)s` / `%(reset)s` tokens from the format string.

The default logging config (`inorbit_connector/logging/logging.default.conf`) references this formatter by class name.


