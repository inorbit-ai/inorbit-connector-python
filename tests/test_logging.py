#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2025 InOrbit, Inc.

# Third-party
import pytest

# InOrbit
from inorbit_connector.logging.logger import LogLevels
from inorbit_connector.models import LoggingConfig


class TestLoggingConfig:
    def test_default_values(self):
        config = LoggingConfig()
        assert config.config_file is not None
        assert config.log_level is None
        assert config.defaults == {
            "log_file": "inorbit-connector.log",
        }

    def test_custom_values(self):
        config = LoggingConfig(
            log_level=LogLevels.INFO, defaults={"log_file": "./test.log"}
        )
        assert config.log_level == LogLevels.INFO
        assert config.defaults == {"log_file": "./test.log"}

    def test_invalid_log_level(self):
        with pytest.raises(
            ValueError,
            match="Input should be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'",
        ):
            LoggingConfig(log_level="BAD")
