# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2025 InOrbit, Inc.

import logging

try:
    import colorlog

    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False


class ConditionalColoredFormatter(logging.Formatter):
    """A formatter that uses colorlog.ColoredFormatter if available,
    otherwise falls back to standard formatting.
    log_colors can be passed in as a dictionary in the defaults section.
    This class is meant to be referenced in logging config files the following way:

    ...
    [formatter_conditional_colored]
    class=inorbit_connector.logging.formatters.ConditionalColoredFormatter
    defaults={'log_colors': {'DEBUG': 'blue','INFO': 'green','WARNING': 'yellow', \
        'ERROR': 'red','CRITICAL': 'bold_red'}}
    ...

    It also allows for the use of colorlog's log_color property.
    """

    def __init__(self, fmt=None, datefmt=None, style="%", defaults=None):
        log_colors = None
        if isinstance(defaults, dict):
            log_colors = defaults.get("log_colors")

        if COLORLOG_AVAILABLE:
            self.formatter = colorlog.ColoredFormatter(
                fmt, datefmt, style, log_colors=log_colors
            )
        else:
            # Remove color codes from format string if colorlog is not available
            fmt = fmt.replace("%(log_color)s", "").replace("%(reset)s", "")
            self.formatter = logging.Formatter(fmt, datefmt, style)

    def format(self, record):
        return self.formatter.format(record)
