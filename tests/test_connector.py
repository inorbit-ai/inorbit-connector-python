#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import logging
from time import sleep
from unittest.mock import Mock, patch, MagicMock

# Third-party
import pytest
from inorbit_edge.models import CameraConfig
from pydantic import BaseModel

# InOrbit
from inorbit_connector.connector import Connector
from inorbit_connector.models import InorbitConnectorConfig


class DummyConfig(BaseModel):
    pass


class TestConnector:

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "api_url": "https://valid.com/",
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture
    def base_connector(self, base_model):
        return Connector("TestRobot", InorbitConnectorConfig(**base_model))

    def test_init(self, base_model):
        config = InorbitConnectorConfig(**base_model)
        robot_id = "TestRobot"

        connector = Connector(robot_id, config)
        assert connector.robot_id == robot_id
        assert connector.config == config

        assert connector._logger.name == Connector.__module__
        assert connector._logger.level == logging.INFO

        assert connector._robot_session.robot_id == robot_id
        assert connector._robot_session.robot_name == robot_id
        assert connector._robot_session.api_key == config.api_key
        assert connector._robot_session.robot_api_key is None
        assert connector._robot_session.endpoint == str(config.api_url)
        assert connector._robot_session.use_ssl is True
        assert connector._robot_session.use_websockets is False

    def test_connect_calls_robot_session_connect(self, base_connector):
        base_connector._robot_session = Mock()
        base_connector._connect()

        assert base_connector._robot_session.connect.called

    def test_connect_raises_error_when_failed_to_connect(self, base_connector):
        base_connector._robot_session = Mock()
        base_connector._robot_session.connect.side_effect = Exception(
            "Failed to connect"
        )

        with pytest.raises(Exception) as e:
            base_connector._connect()
        assert str(e.value) == "Failed to connect"

    def test_disconnect(self, base_connector):
        base_connector._robot_session = Mock()
        base_connector._disconnect()

        assert base_connector._robot_session.disconnect.called

    def test_execution_loop(self, base_connector):
        with patch("logging.Logger.warning", new=MagicMock()) as mock_warning:
            mock_warning.assert_not_called()
            base_connector._execution_loop()
            mock_warning.assert_called_once_with("Execution loop is empty.")

    def test_start(self, base_model):
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch("threading.Thread") as mock_thread:
            connector._connect = MagicMock()
            connector.start()
            connector._connect.assert_called_once()
            mock_thread.assert_called()
            mock_thread().start.assert_called_once()

    def test_start_with_cameras(self, base_model):
        base_model["cameras"] = [CameraConfig(video_url="https://test.com/")]
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch("threading.Thread") as mock_thread:
            connector._connect = MagicMock()
            connector._robot_session = MagicMock()
            connector.start()
            connector._connect.assert_called_once()
            mock_thread.assert_called()
            mock_thread().start.assert_called_once()

            connector._connect.assert_called_once()

            assert connector._robot_session.register_camera.call_count == len(
                connector.config.cameras
            )

            mock_thread.assert_called()
            mock_thread().start.assert_called_once()

    def test_start_with_cameras_none_params_ignored(self, base_model):
        base_model["cameras"] = [CameraConfig(video_url="https://test.com/")]
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch("threading.Thread") as mock_thread:
            connector._connect = MagicMock()
            connector.start()

            assert len(connector._robot_session.camera_streamers.keys()) == len(
                connector.config.cameras
            )
            assert "0" in connector._robot_session.camera_streamers.keys()
            streamer = connector._robot_session.camera_streamers["0"]
            assert streamer.camera.video_url == str(base_model["cameras"][0].video_url)
            assert streamer.camera.rate == 10
            assert streamer.camera.scaling == 0.3
            assert streamer.camera.quality == 35

            connector._connect.assert_called_once()
            mock_thread.assert_called()
            mock_thread().start.assert_called_once()
            connector._connect.assert_called_once()
            mock_thread.assert_called()
            mock_thread().start.assert_called_once()

    def test_start_with_cameras_custom_params(self, base_model):
        base_model["cameras"] = [
            CameraConfig(video_url="https://test.com/", rate=5, scaling=0.2, quality=30)
        ]
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch("threading.Thread") as mock_thread:
            connector._connect = MagicMock()
            connector.start()

            assert len(connector._robot_session.camera_streamers.keys()) == len(
                connector.config.cameras
            )
            assert "0" in connector._robot_session.camera_streamers.keys()
            streamer = connector._robot_session.camera_streamers["0"]
            assert streamer.camera.rate == 5
            assert streamer.camera.scaling == 0.2
            assert streamer.camera.quality == 30
            assert streamer.camera.video_url == str(base_model["cameras"][0].video_url)

            connector._connect.assert_called_once()
            mock_thread.assert_called()
            mock_thread().start.assert_called_once()
            connector._connect.assert_called_once()
            mock_thread.assert_called()
            mock_thread().start.assert_called_once()

    def test_stop(self, base_connector):
        with (
            patch.object(base_connector, "_disconnect") as mock_disconnect,
            patch("threading.Event.set") as mock_thread_set,
            patch("threading.Thread.join") as mock_thread_join,
        ):
            base_connector.stop()

            assert mock_disconnect.called
            assert mock_thread_set.called
            assert mock_thread_join.called

    def test_run(self, base_model):
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        connector._execution_loop = MagicMock()
        connector._robot_session = Mock()

        connector.start()
        sleep(1.0 / connector.config.update_freq)
        connector.stop()
        connector._execution_loop.assert_called()

        connector._execution_loop.reset_mock()
        sleep((1.0 / connector.config.update_freq) * 2)
        connector._execution_loop.assert_not_called()
