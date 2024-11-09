#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import os
import logging
from time import sleep
from unittest.mock import Mock, patch, MagicMock

# Third-party
import pytest
from inorbit_edge.models import CameraConfig
from inorbit_edge.robot import RobotSession
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

    def test_publish_map(self, base_model):
        # Test with no maps
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch.object(connector._robot_session, "publish_map") as mock_publish:
            connector.publish_map("map")
            mock_publish.assert_not_called()

        # Test with a map
        base_model["maps"] = {
            "frameA": {
                "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                "map_id": "valid_map_id",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
            }
        }
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch.object(connector._robot_session, "publish_map") as mock_publish:
            connector.publish_map("frameA")
            mock_publish.assert_called_once()

    def test_publish_pose_updates_maps(self, base_model):
        base_model["maps"] = {
            "frameA": {
                "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                "map_id": "valid_map_id",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
            },
            "frameB": {
                "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                "map_id": "valid_map_id",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
            },
        }
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch.object(connector._robot_session, "publish_map") as mock_publish_map:
            connector.publish_pose(0, 0, 0, "frameA")
            assert mock_publish_map.call_count == 1  # Called on first map publish
            connector.publish_pose(0, 0, 0, "frameA")
            assert mock_publish_map.call_count == 1  # Not called again
            connector.publish_pose(0, 0, 0, "frameB")
            assert mock_publish_map.call_count == 2  # Called again

    def test_register_user_scripts(self, base_model, tmp_path):
        with patch(
            f"{RobotSession.__module__}.{RobotSession.__name__}"
            ".register_commands_path",
            autospec=True,
        ) as mock_register_path:
            # Test it doesn't register callbacks if no user scripts are specified
            Connector("TestRobot", InorbitConnectorConfig(**base_model))
            mock_register_path.assert_not_called()
            mock_register_path.reset_mock()

            # Test it attepts to registers callbacks if user scripts are specified, but
            # fails if the directory does not exist
            Connector(
                "TestRobot",
                InorbitConnectorConfig(**base_model),
                register_user_scripts=True,
                default_user_scripts_dir=tmp_path / "./not_a_dir",
            )
            mock_register_path.assert_not_called()
            mock_register_path.reset_mock()

            # Test it attepts to registers callbacks if user scripts are specified and
            # the directory exists
            Connector(
                "TestRobot",
                InorbitConnectorConfig(**base_model),
                register_user_scripts=True,
                default_user_scripts_dir=tmp_path,
            )
            mock_register_path.assert_called_once()
            mock_register_path.reset_mock()

            # Test it creates the scripts folder if specified
            Connector(
                "TestRobot",
                InorbitConnectorConfig(**base_model),
                register_user_scripts=True,
                default_user_scripts_dir=tmp_path / "a_dir",
                create_user_scripts_dir=True,
            )
            mock_register_path.assert_called_once()
            mock_register_path.reset_mock()

    def test_register_command_callback(self, base_model):
        with patch(
            f"{Connector.__module__}.{Connector.__name__}"
            "._register_custom_command_handler",
            autospec=True,
        ) as mock_register_callback:
            # Test it registers by default
            Connector("TestRobot", InorbitConnectorConfig(**base_model))
            mock_register_callback.assert_called_once()
            mock_register_callback.reset_mock()

            # Test it doesn't register if explicitly disabled
            Connector(
                "TestRobot",
                InorbitConnectorConfig(**base_model),
                register_custom_command_handler=False,
            )
            mock_register_callback.assert_not_called()
