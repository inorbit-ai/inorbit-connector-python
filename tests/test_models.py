#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import importlib
import os
import re
import sys
from unittest import mock

# Third-party
import pytest
from inorbit_edge.models import CameraConfig
from inorbit_edge.robot import INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL
from pydantic import ValidationError, BaseModel

# InOrbit
from inorbit_connector.models import InorbitConnectorConfig
from inorbit_connector.utils import LogLevels


class DummyConfig(BaseModel):
    pass


class InvalidDummyConfig(IndexError):
    pass


class TestInorbitConnectorConfig:

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "api_url": "https://valid.com/",
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
            "update_freq": 2.0,
            "location_tz": "Asia/Kolkata",
            "log_level": LogLevels.INFO,
        }

    def test_with_valid_input(self, base_model):
        model = InorbitConnectorConfig(**base_model)
        assert model.api_key == base_model["api_key"]
        assert str(model.api_url) == base_model["api_url"]
        assert model.connector_type == base_model["connector_type"]
        assert isinstance(model.connector_config, DummyConfig)
        assert model.update_freq == base_model["update_freq"]
        assert model.location_tz == base_model["location_tz"]
        assert model.log_level == base_model["log_level"]
        assert model.cameras == []
        assert model.user_scripts_dir is None

    def test_with_valid_input_and_user_scripts_dir(self, base_model):
        model = InorbitConnectorConfig(**base_model, user_scripts_dir=".")
        assert str(model.user_scripts_dir) == "."

    def test_with_valid_input_and_cameras(self, base_model):
        model = InorbitConnectorConfig(
            **base_model, cameras=[CameraConfig(video_url="https://test.com/")]
        )
        assert len(model.cameras) == 1
        assert str(model.cameras[0].video_url) == "https://test.com/"

    def test_invalid_api_key(self, base_model):
        init_input = base_model.copy()
        init_input["api_key"] = "key with spaces"
        with pytest.raises(ValidationError, match="Whitespaces are not allowed"):
            InorbitConnectorConfig(**init_input)

    def test_invalid_account_id(self, base_model):
        init_input = base_model.copy()
        init_input["account_id"] = "account id with spaces"
        with pytest.raises(ValidationError, match="Whitespaces are not allowed"):
            InorbitConnectorConfig(**init_input)

    def test_invalid_connector_config(self, base_model):
        init_input = {
            "connector_type": "valid_connector",
            "connector_config": InvalidDummyConfig(),
        }

        error = (
            "1 validation error for InorbitConnectorConfig\nconnector_config\n  "
            "Input should be a valid dictionary or instance of BaseModel "
            "[type=model_type, input_value=InvalidDummyConfig(), "
            "input_type=InvalidDummyConfig]\n    For further information visit "
            "https://errors.pydantic.dev/2.7/v/model_type"
        )
        with pytest.raises(ValidationError, match=re.escape(error)):
            InorbitConnectorConfig(**init_input)

    def test_invalid_location_tz(self, base_model):
        init_input = base_model.copy()
        init_input["location_tz"] = "invalid_tz"
        with pytest.raises(ValidationError, match="Timezone must exist in pytz"):
            InorbitConnectorConfig(**init_input)

    def test_invalid_update_freq(self, base_model):
        init_input = base_model.copy()
        init_input["update_freq"] = -2.0
        with pytest.raises(ValidationError, match="Must be positive and non-zero"):
            InorbitConnectorConfig(**init_input)

        init_input["update_freq"] = 0.0
        with pytest.raises(ValidationError, match="Must be positive and non-zero"):
            InorbitConnectorConfig(**init_input)

    def test_invalid_log_level(self, base_model):
        init_input = base_model.copy()
        init_input["log_level"] = "BAD"

        error = (
            "1 validation error for InorbitConnectorConfig\nlog_level\n  Input "
            "should be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL' [type=enum, "
            "input_value='BAD', input_type=str]\n    For further information visit "
            "https://errors.pydantic.dev/2.7/v/enum"
        )
        with pytest.raises(ValidationError, match=re.escape(error)):
            InorbitConnectorConfig(**init_input)

    def test_invalid_user_scripts_dir(self, base_model):
        init_input = base_model.copy()
        init_input["user_scripts_dir"] = "/does/not/exist"
        with pytest.raises(ValidationError, match="Must be a valid directory"):
            InorbitConnectorConfig(**init_input)

    @mock.patch.dict(os.environ, {"INORBIT_API_KEY": "env_valid_key"})
    def test_reads_api_key_from_environment_variable(self, base_model):
        # Re-import after Mock
        importlib.reload(sys.modules["inorbit_connector.models"])
        from inorbit_connector.models import InorbitConnectorConfig

        init_input = {
            "api_url": "https://valid.video_url/",
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }
        model = InorbitConnectorConfig(**init_input)
        assert model.api_key == "env_valid_key"

    @mock.patch.dict(os.environ, {"INORBIT_API_URL": "https://valid.env/"})
    def test_reads_api_url_from_environment_variable(self, base_model):
        # Re-import after Mock
        importlib.reload(sys.modules["inorbit_connector.models"])
        from inorbit_connector.models import InorbitConnectorConfig

        init_input = {
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }
        model = InorbitConnectorConfig(**init_input)
        assert str(model.api_url) == "https://valid.env/"

    def test_reads_api_url_from_environment_variable_default(self, base_model):
        init_input = {
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }
        model = InorbitConnectorConfig(**init_input)
        assert str(model.api_url) == INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL

    def test_missing_api_key_environment_variable(self, base_model):
        init_input = {
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }
        model = InorbitConnectorConfig(**init_input)
        assert model.api_key is None
