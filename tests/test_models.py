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
    ConnectorConfig,
    MapConfig,
    MapConfigBase,
    MapConfigTemp,
    MetricsConfig,
    RobotConfig,
    LoggingConfig,
)
from pathlib import Path
from inorbit_connector.logging.logger import LogLevels


class DummyConfig(BaseModel):
    pass


class InvalidDummyConfig(IndexError):
    pass


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

    def test_use_websockets_defaults_to_false(self, base_model):
        model = ConnectorConfig(**base_model)
        assert model.use_websockets is False

    def test_use_websockets_can_be_enabled(self, base_model):
        init_input = base_model.copy()
        init_input["use_websockets"] = True
        model = ConnectorConfig(**init_input)
        assert model.use_websockets is True

    def test_use_websockets_must_be_bool(self, base_model):
        init_input = base_model.copy()
        init_input["use_websockets"] = "not-a-bool"
        with pytest.raises(ValidationError):
            ConnectorConfig(**init_input)

    def test_use_websockets_preserved_in_to_singular_config(self, base_model):
        init_input = base_model.copy()
        init_input["use_websockets"] = True
        model = ConnectorConfig(**init_input)
        singular = model.to_singular_config("robot1")
        assert singular.use_websockets is True

    @mock.patch.dict(os.environ, {"INORBIT_API_KEY": "env_valid_key"})
    def test_reads_api_key_from_environment_variable(self, base_model):
        importlib.reload(sys.modules["inorbit_connector.models"])
        from inorbit_connector.models import ConnectorConfig as ReloadedConfig

        init_input = {
            "api_url": "https://valid.video_url/",
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
            "fleet": [{"robot_id": "robot1"}],
        }
        model = ReloadedConfig(**init_input)
        assert model.api_key == "env_valid_key"

    @mock.patch.dict(os.environ, {"INORBIT_API_URL": "https://valid.env/"})
    def test_reads_api_url_from_environment_variable(self, base_model):
        importlib.reload(sys.modules["inorbit_connector.models"])
        from inorbit_connector.models import ConnectorConfig as ReloadedConfig

        init_input = {
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
            "fleet": [{"robot_id": "robot1"}],
        }
        model = ReloadedConfig(**init_input)
        assert str(model.api_url) == "https://valid.env/"

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_reads_api_url_from_environment_variable_default(self, base_model):
        importlib.reload(sys.modules["inorbit_connector.models"])
        from inorbit_connector.models import ConnectorConfig as ReloadedConfig

        init_input = {
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
            "fleet": [{"robot_id": "robot1"}],
        }
        model = ReloadedConfig(**init_input)
        assert str(model.api_url) == INORBIT_CLOUD_SDK_ROBOT_CONFIG_URL

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_environment_variable(self, base_model):
        importlib.reload(sys.modules["inorbit_connector.models"])
        from inorbit_connector.models import ConnectorConfig as ReloadedConfig

        init_input = {
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
            "fleet": [{"robot_id": "robot1"}],
        }
        model = ReloadedConfig(**init_input)
        assert model.api_key is None


class TestMapConfigBase:
    """Tests for the MapConfigBase model."""

    def test_valid_map_config_base(self):
        """Test creating a valid MapConfigBase instance."""
        config = MapConfigBase(
            map_id="test_map",
            origin_x=1.0,
            origin_y=2.0,
            resolution=0.05,
        )
        assert config.map_id == "test_map"
        assert config.map_label is None
        assert config.origin_x == 1.0
        assert config.origin_y == 2.0
        assert config.resolution == 0.05
        assert config.format_version == 2

    def test_map_config_base_with_label(self):
        """Test MapConfigBase with optional map_label."""
        config = MapConfigBase(
            map_id="test_map",
            map_label="Test Map Label",
            origin_x=0.0,
            origin_y=0.0,
            resolution=0.1,
        )
        assert config.map_label == "Test Map Label"

    def test_map_config_base_format_version_validation(self):
        """Test that format_version must be 1 or 2."""
        with pytest.raises(ValidationError, match="format_version must be 1 or 2"):
            MapConfigBase(
                map_id="test_map",
                origin_x=0.0,
                origin_y=0.0,
                resolution=0.1,
                format_version=3,
            )

    def test_map_config_base_format_version_accepts_1(self):
        """Test that format_version accepts value 1."""
        config = MapConfigBase(
            map_id="test_map",
            origin_x=0.0,
            origin_y=0.0,
            resolution=0.1,
            format_version=1,
        )
        assert config.format_version == 1


class TestMapConfigTemp:
    """Tests for the MapConfigTemp model."""

    def test_valid_map_config_temp(self):
        """Test creating a valid MapConfigTemp instance."""
        image_bytes = b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
        config = MapConfigTemp(
            image=image_bytes,
            map_id="temp_map",
            origin_x=0.0,
            origin_y=0.0,
            resolution=0.05,
        )
        assert config.image == image_bytes
        assert config.map_id == "temp_map"
        assert config.format_version == 2

    def test_map_config_temp_inherits_from_base(self):
        """Test that MapConfigTemp inherits from MapConfigBase."""
        assert issubclass(MapConfigTemp, MapConfigBase)

    def test_map_config_temp_has_no_file_field(self):
        """Test that MapConfigTemp does not have a file field."""
        config = MapConfigTemp(
            image=b"test",
            map_id="temp_map",
            origin_x=0.0,
            origin_y=0.0,
            resolution=0.05,
        )
        assert not hasattr(config, "file") or "file" not in config.model_fields

    def test_map_config_temp_model_dump(self):
        """Test that model_dump works correctly for MapConfigTemp."""
        image_bytes = b"test_image_data"
        config = MapConfigTemp(
            image=image_bytes,
            map_id="temp_map",
            map_label="Temp Label",
            origin_x=1.0,
            origin_y=2.0,
            resolution=0.1,
            format_version=1,
        )
        dumped = config.model_dump()
        assert dumped["image"] == image_bytes
        assert dumped["map_id"] == "temp_map"
        assert dumped["map_label"] == "Temp Label"
        assert dumped["origin_x"] == 1.0
        assert dumped["origin_y"] == 2.0
        assert dumped["resolution"] == 0.1
        assert dumped["format_version"] == 1


class TestMapConfig:
    """Tests for the MapConfig model."""

    def test_map_config_inherits_from_base(self):
        """Test that MapConfig inherits from MapConfigBase."""
        assert issubclass(MapConfig, MapConfigBase)

    def test_map_config_requires_file(self):
        """Test that MapConfig requires a file field."""
        with pytest.raises(ValidationError):
            MapConfig(
                map_id="test_map",
                origin_x=0.0,
                origin_y=0.0,
                resolution=0.1,
            )

    def test_map_config_validates_png_file(self):
        """Test that MapConfig validates file is a PNG."""
        with pytest.raises(ValidationError, match="The map file must be a PNG file"):
            MapConfig(
                file=f"{os.path.dirname(__file__)}/dir/not_a_map.txt",
                map_id="test_map",
                origin_x=0.0,
                origin_y=0.0,
                resolution=0.1,
            )

    def test_map_config_with_valid_png(self):
        """Test MapConfig with a valid PNG file."""
        config = MapConfig(
            file=f"{os.path.dirname(__file__)}/dir/test_map.png",
            map_id="test_map",
            origin_x=0.0,
            origin_y=0.0,
            resolution=0.1,
        )
        assert config.map_id == "test_map"
        assert config.format_version == 2


class TestMetricsConfig:
    """Tests for the opt-in metrics configuration."""

    def test_defaults(self):
        cfg = MetricsConfig()
        assert cfg.enabled is False
        assert cfg.bind_host == "0.0.0.0"
        assert cfg.bind_port == 9090
        assert cfg.advertise_host is None
        assert cfg.discovery_dir == Path("/var/run/inorbit-metrics")
        assert cfg.connector_id is None
        assert cfg.exporter_namespace is None
        assert cfg.extra_resource_attributes == {}

    def test_exporter_namespace_rejects_hyphens(self):
        with pytest.raises(ValidationError):
            MetricsConfig(exporter_namespace="inorbit-connector")

    def test_exporter_namespace_rejects_leading_digit(self):
        with pytest.raises(ValidationError):
            MetricsConfig(exporter_namespace="1connector")

    def test_exporter_namespace_accepts_underscores_and_digits(self):
        cfg = MetricsConfig(exporter_namespace="inorbit_connector_v2")
        assert cfg.exporter_namespace == "inorbit_connector_v2"

    def test_exporter_namespace_accepts_none_for_auto_derive(self):
        # None means setup_prometheus_metrics derives
        # `inorbit_<connector_type>_connector` at install time.
        cfg = MetricsConfig(exporter_namespace=None)
        assert cfg.exporter_namespace is None

    def test_extra_resource_attributes_rejects_empty_values(self):
        with pytest.raises(ValidationError):
            MetricsConfig(extra_resource_attributes={"site": ""})

    def test_extra_resource_attributes_rejects_invalid_keys(self):
        with pytest.raises(ValidationError):
            MetricsConfig(extra_resource_attributes={"has-hyphen": "ok"})

    def test_extra_resource_attributes_accepts_valid_pairs(self):
        cfg = MetricsConfig(
            extra_resource_attributes={"site": "lab", "region": "us"}
        )
        assert cfg.extra_resource_attributes == {"site": "lab", "region": "us"}

    def test_discovery_dir_accepts_none(self):
        """discovery_dir=None opts out of writing the file_sd discovery file."""
        cfg = MetricsConfig(discovery_dir=None)
        assert cfg.discovery_dir is None


def test_connector_config_includes_metrics_with_default():
    cfg = ConnectorConfig(
        api_key="ak",
        connector_type="test",
        connector_config=DummyConfig(),
        fleet=[{"robot_id": "r1"}],
    )
    assert isinstance(cfg.metrics, MetricsConfig)
    assert cfg.metrics.enabled is False
