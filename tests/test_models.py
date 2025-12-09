#!/usr/bin/env python

# Copyright 2024 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

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
from inorbit_connector.models import (
    InorbitConnectorConfig,
    ConnectorConfig,
    RobotConfig,
    LoggingConfig,
)
from inorbit_connector.logging.logger import LogLevels


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
            "logging": LoggingConfig(defaults={"log_file": "./test.log"}),
        }

    def test_with_valid_input(self, base_model):
        model = InorbitConnectorConfig(**base_model)
        assert model.api_key == base_model["api_key"]
        assert str(model.api_url) == base_model["api_url"]
        assert model.connector_type == base_model["connector_type"]
        assert isinstance(model.connector_config, DummyConfig)
        assert model.update_freq == base_model["update_freq"]
        assert model.location_tz == base_model["location_tz"]
        assert model.cameras == []
        assert model.user_scripts_dir is None
        assert model.logging == base_model["logging"]
        assert model.account_id is None
        assert model.inorbit_robot_key is None
        assert model.maps == {}
        assert model.env_vars == {}

    def test_with_valid_input_and_user_scripts_dir(self, base_model):
        model = InorbitConnectorConfig(**base_model, user_scripts_dir=".")
        assert str(model.user_scripts_dir) == "."

    def test_with_valid_input_and_cameras(self, base_model):
        model = InorbitConnectorConfig(
            **base_model, cameras=[CameraConfig(video_url="https://test.com/")]
        )
        assert len(model.cameras) == 1
        assert str(model.cameras[0].video_url) == "https://test.com/"

    def test_with_valid_input_and_maps(self, base_model):
        model = InorbitConnectorConfig(
            **base_model,
            maps={
                "frameA": {
                    "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                    "map_id": "valid_map_id",
                    "origin_x": 0.0,
                    "origin_y": 0.0,
                    "resolution": 0.1,
                    "formatVersion": 2,
                }
            },
        )
        assert len(model.maps.keys()) == 1

    def test_format_version_valid_values(self, base_model):
        model_1 = InorbitConnectorConfig(
            **base_model,
            maps={
                "frameA": {
                    "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                    "map_id": "valid_map_id",
                    "origin_x": 0.0,
                    "origin_y": 0.0,
                    "resolution": 0.1,
                    "formatVersion": 1,
                }
            },
        )
        model_2 = InorbitConnectorConfig(
            **base_model,
            maps={
                "frameA": {
                    "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                    "map_id": "valid_map_id",
                    "origin_x": 0.0,
                    "origin_y": 0.0,
                    "resolution": 0.1,
                    "formatVersion": 2,
                }
            },
        )
        model_null = InorbitConnectorConfig(
            **base_model,
            maps={
                "frameA": {
                    "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                    "map_id": "valid_map_id",
                    "origin_x": 0.0,
                    "origin_y": 0.0,
                    "resolution": 0.1,
                    "formatVersion": None,
                }
            },
        )
        model_empty = InorbitConnectorConfig(
            **base_model,
            maps={
                "frameA": {
                    "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                    "map_id": "valid_map_id",
                    "origin_x": 0.0,
                    "origin_y": 0.0,
                    "resolution": 0.1,
                }
            },
        )

    def test_with_valid_input_and_env_vars(self, base_model):
        model = InorbitConnectorConfig(
            **base_model,
            env_vars={"ENV_VAR": "env_value"},
        )
        assert model.env_vars == {"ENV_VAR": "env_value"}

    def test_with_valid_input_and_logging_config(self, base_model):
        logging_config = LoggingConfig(
            log_level=LogLevels.INFO, defaults={"log_file": "./test.log"}
        )
        base_model = base_model.copy()
        base_model.pop("logging", None)
        model = InorbitConnectorConfig(
            **base_model,
            logging=logging_config,
        )
        assert model.logging.log_level == LogLevels.INFO
        assert model.logging.defaults == {"log_file": "./test.log"}

    def test_with_valid_input_and_account_id(self, base_model):
        model = InorbitConnectorConfig(
            **base_model,
            account_id="valid_account_id",
        )
        assert model.account_id == "valid_account_id"

    def test_with_valid_input_and_robot_key(self, base_model):
        model = InorbitConnectorConfig(
            **base_model,
            inorbit_robot_key="valid_robot_key",
        )
        assert model.inorbit_robot_key == "valid_robot_key"

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

        error = re.escape(
            "1 validation error for InorbitConnectorConfig\nconnector_config\n  "
            "Input should be a valid dictionary or instance of BaseModel "
            "[type=model_type, input_value=InvalidDummyConfig(), "
            "input_type=InvalidDummyConfig]\n    For further information visit "
        )
        with pytest.raises(ValidationError, match=error):
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
        init_input["logging"] = {"log_level": "BAD"}
        error = r"Input should be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'"
        with pytest.raises(ValidationError, match=error):
            InorbitConnectorConfig(**init_input)

    def test_invalid_user_scripts_dir(self, base_model):
        init_input = base_model.copy()
        init_input["user_scripts_dir"] = "/does/not/exist"

        error = (
            "1 validation error for InorbitConnectorConfig\nuser_scripts_dir\n  "
            "Path does not point to a directory [type=path_not_directory, input_value="
            "'/does/not/exist', input_type=str]"
        )
        with pytest.raises(ValidationError, match=re.escape(error)):
            InorbitConnectorConfig(**init_input)

    def test_invalid_maps(self, base_model):
        init_input = base_model.copy()
        init_input["maps"] = {
            "frameA": {
                "file": f"{os.path.dirname(__file__)}/dir/invalid_map.png",
                "map_id": "valid_map_id",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
                "formatVersion": 2,
            }
        }
        with pytest.raises(ValidationError, match="Path does not point to a file"):
            InorbitConnectorConfig(**init_input)
        init_input = base_model.copy()
        init_input["maps"] = {
            "frameA": {
                "file": f"{os.path.dirname(__file__)}/dir/not_a_map.txt",
                "map_id": "valid_map_id",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
                "formatVersion": 2,
            }
        }
        with pytest.raises(ValidationError, match="The map file must be a PNG file"):
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

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_reads_api_url_from_environment_variable_default(self, base_model):
        # Re-import after Mock
        importlib.reload(sys.modules["inorbit_connector.models"])
        from inorbit_connector.models import InorbitConnectorConfig

        init_input = {
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }
        model = InorbitConnectorConfig(**init_input)
        assert str(model.api_url) == INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_environment_variable(self, base_model):
        # Re-import after Mock
        importlib.reload(sys.modules["inorbit_connector.models"])
        from inorbit_connector.models import InorbitConnectorConfig

        init_input = {
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }
        model = InorbitConnectorConfig(**init_input)
        assert model.api_key is None


class TestRobotConfig:
    def test_with_valid_input(self):
        robot_config = RobotConfig(robot_id="test_robot")
        assert robot_config.robot_id == "test_robot"
        assert robot_config.cameras == []

    def test_with_cameras(self):
        robot_config = RobotConfig(
            robot_id="test_robot",
            cameras=[CameraConfig(video_url="https://test.com/")],
        )
        assert robot_config.robot_id == "test_robot"
        assert len(robot_config.cameras) == 1
        assert str(robot_config.cameras[0].video_url) == "https://test.com/"


class TestConnectorConfig:
    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "api_url": "https://valid.com/",
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
            "fleet": [
                {"robot_id": "robot1"},
                {"robot_id": "robot2"},
            ],
        }

    def test_with_valid_input(self, base_model):
        model = ConnectorConfig(**base_model)
        assert model.api_key == base_model["api_key"]
        assert str(model.api_url) == base_model["api_url"]
        assert model.connector_type == base_model["connector_type"]
        assert isinstance(model.connector_config, DummyConfig)
        assert len(model.fleet) == 2
        assert model.fleet[0].robot_id == "robot1"
        assert model.fleet[1].robot_id == "robot2"

    def test_fleet_must_contain_at_least_one_robot(self, base_model):
        init_input = base_model.copy()
        init_input["fleet"] = []
        with pytest.raises(
            ValidationError, match="Fleet must contain at least one robot"
        ):
            ConnectorConfig(**init_input)

    def test_robot_ids_must_be_unique(self, base_model):
        init_input = base_model.copy()
        init_input["fleet"] = [
            {"robot_id": "robot1"},
            {"robot_id": "robot1"},
        ]
        with pytest.raises(ValidationError, match="Robot ids must be unique"):
            ConnectorConfig(**init_input)

    def test_with_robot_cameras(self, base_model):
        init_input = base_model.copy()
        init_input["fleet"] = [
            {
                "robot_id": "robot1",
                "cameras": [CameraConfig(video_url="https://test.com/")],
            },
        ]
        model = ConnectorConfig(**init_input)
        assert len(model.fleet[0].cameras) == 1
        assert str(model.fleet[0].cameras[0].video_url) == "https://test.com/"

    def test_to_singular_config(self, base_model):
        model = ConnectorConfig(**base_model)
        singular = model.to_singular_config("robot1")
        assert len(singular.fleet) == 1
        assert singular.fleet[0].robot_id == "robot1"
        assert singular.connector_type == model.connector_type
        assert singular.api_key == model.api_key

    def test_to_singular_config_invalid_robot_id(self, base_model):
        model = ConnectorConfig(**base_model)
        with pytest.raises(
            ValueError,
            match="Expected 1 robot configuration for robot invalid_robot, got 0",
        ):
            model.to_singular_config("invalid_robot")

    def test_to_singular_config_preserves_subclass_type(self, base_model):
        class CustomConnectorConfig(ConnectorConfig):
            pass

        model = CustomConnectorConfig(**base_model)
        singular = model.to_singular_config("robot1")
        assert isinstance(singular, CustomConnectorConfig)


class TestInorbitConnectorConfigToFleetConfig:
    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "api_url": "https://valid.com/",
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    def test_to_fleet_config(self, base_model):
        model = InorbitConnectorConfig(**base_model)
        fleet_config = model.to_fleet_config("test_robot")
        assert type(fleet_config).__name__ == "ConnectorConfig"
        assert len(fleet_config.fleet) == 1
        assert fleet_config.fleet[0].robot_id == "test_robot"
        assert fleet_config.connector_type == model.connector_type
        assert fleet_config.api_key == model.api_key

    def test_to_fleet_config_with_cameras(self, base_model):
        model = InorbitConnectorConfig(
            **base_model, cameras=[CameraConfig(video_url="https://test.com/")]
        )
        fleet_config = model.to_fleet_config("test_robot")
        assert len(fleet_config.fleet[0].cameras) == 1
        assert str(fleet_config.fleet[0].cameras[0].video_url) == "https://test.com/"
