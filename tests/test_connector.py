#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import os
import logging
from time import sleep
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path

# Third-party
import pytest
from pydantic import AnyHttpUrl
from inorbit_edge.models import CameraConfig
from inorbit_edge.robot import RobotSession
from pydantic import BaseModel

# InOrbit
from inorbit_connector.connector import (
    Connector,
    InorbitConnectorConfig,
)


class DummyConfig(BaseModel):
    pass


class TestConnectorIsAbstract:
    def test_connector_is_abstract(self):
        assert Connector.__abstractmethods__ == {
            "_connect",
            "_disconnect",
            "_execution_loop",
            "_inorbit_command_handler",
        }

    def test_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            Connector("TestRobot", MagicMock())

    def test_cannot_be_subclassed_without_overriding_abstract_methods(self):
        class SubConnector(Connector):
            pass

        with pytest.raises(TypeError):
            SubConnector("TestRobot", MagicMock())

    def test_can_be_subclassed_with_all_abstract_methods_implemented(self):
        class SubConnector(Connector):
            def _connect(self):
                pass

            def _disconnect(self):
                pass

            def _execution_loop(self):
                pass

            def _inorbit_command_handler(self, command_name, args, options):
                pass

        connector = SubConnector(
            "TestRobot",
            InorbitConnectorConfig(
                api_key="valid_key",
                api_url="https://valid.com/",
                connector_type="valid_connector",
                connector_config=DummyConfig(),
            ),
        )
        assert isinstance(connector, Connector)


class TestConnector:

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "api_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_connector_not_abstract(self):
        Connector.__abstractmethods__ = set()

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
        assert logging.getLogger().level == logging.INFO

        assert connector._robot_session.robot_id == robot_id
        assert connector._robot_session.robot_name == robot_id
        assert connector._robot_session.api_key == config.api_key
        assert connector._robot_session.robot_api_key is None
        assert connector._robot_session.endpoint == str(config.api_url)
        assert connector._robot_session.use_ssl is True
        assert connector._robot_session.use_websockets is False
        assert connector._robot_session.robot_key is None

    def test_init_with_robot_key(self, base_model):
        config = InorbitConnectorConfig(
            **base_model, inorbit_robot_key="valid_robot_key"
        )
        robot_id = "TestRobot"

        connector = Connector(robot_id, config)
        assert connector._robot_session.robot_key == "valid_robot_key"

    @pytest.mark.asyncio
    async def test_connect_calls_robot_session_connect(self, base_connector):
        base_connector._robot_session = Mock()
        base_connector._connect = AsyncMock()
        await base_connector._Connector__connect()

        assert base_connector._connect.called
        assert base_connector._robot_session.connect.called

    @pytest.mark.asyncio
    async def test_connect_raises_error_when_failed_to_connect(self, base_connector):
        base_connector._robot_session = Mock()
        base_connector._robot_session.connect.side_effect = Exception(
            "Failed to connect"
        )

        with pytest.raises(Exception) as e:
            await base_connector._Connector__connect()
        assert str(e.value) == "Failed to connect"

    @pytest.mark.asyncio
    async def test_disconnect(self, base_connector):
        base_connector._robot_session = Mock()
        base_connector._disconnect = AsyncMock()
        await base_connector._Connector__disconnect()

        assert base_connector._disconnect.called
        assert base_connector._robot_session.disconnect.called

    def test_start(self, base_model):
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch("threading.Thread") as mock_thread:
            connector._Connector__run_connector = MagicMock()
            connector.start()
            assert not connector._Connector__stop_event.is_set()
            mock_thread.assert_called_with(target=connector._Connector__run_connector)
            mock_thread().start.assert_called_once()

    def test_run_connector(self, base_connector):
        run_connector = base_connector._Connector__run_connector

        with (
            patch("asyncio.new_event_loop") as mock_loop,
            patch("asyncio.set_event_loop") as mock_set_loop,
        ):

            # Setup mocks
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop
            base_connector._Connector__connect = AsyncMock()
            base_connector._Connector__run_loop = AsyncMock()
            base_connector._Connector__disconnect = AsyncMock()
            base_connector._robot_session = MagicMock()

            # Call the method
            run_connector()

            # Verify the event loop was created and set
            mock_loop.assert_called_once()
            mock_set_loop.assert_called_once_with(mock_event_loop)

            # Verify connect was called
            base_connector._Connector__connect.assert_called_once()

            # Verify run_loop was called
            base_connector._Connector__run_loop.assert_called_once()

            # Verify disconnect was called in the finally block
            base_connector._Connector__disconnect.assert_called_once()

            # Verify the loop was closed
            mock_event_loop.close.assert_called_once()

    def test_run_with_cameras(self, base_model):
        base_model["cameras"] = [CameraConfig(video_url="https://test.com/")]
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        run_connector = connector._Connector__run_connector

        with (
            patch("asyncio.new_event_loop") as mock_loop,
            patch("asyncio.set_event_loop"),
        ):

            # Setup mocks
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop
            connector._Connector__connect = AsyncMock()
            connector._Connector__run_loop = AsyncMock()
            connector._Connector__disconnect = AsyncMock()
            connector._robot_session.register_camera = MagicMock()

            # Call the method
            run_connector()

            assert connector._robot_session.register_camera.call_count == len(
                connector.config.cameras
            )

    def test_run_with_cameras_none_params_ignored(self, base_model):
        base_model["cameras"] = [CameraConfig(video_url="https://test.com/")]
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        run_connector = connector._Connector__run_connector

        with (
            patch("asyncio.new_event_loop") as mock_loop,
            patch("asyncio.set_event_loop"),
        ):

            # Setup mocks
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop
            connector._Connector__connect = AsyncMock()
            connector._Connector__run_loop = AsyncMock()
            connector._Connector__disconnect = AsyncMock()

            # Call the method
            run_connector()

            assert len(connector._robot_session.camera_streamers.keys()) == len(
                connector.config.cameras
            )
            assert "0" in connector._robot_session.camera_streamers.keys()
            streamer = connector._robot_session.camera_streamers["0"]
            assert streamer.camera.video_url == str(base_model["cameras"][0].video_url)
            assert streamer.camera.rate == 10
            assert streamer.camera.scaling == 0.3
            assert streamer.camera.quality == 35

    def test_run_with_cameras_custom_params(self, base_model):
        base_model["cameras"] = [
            CameraConfig(video_url="https://test.com/", rate=5, scaling=0.2, quality=30)
        ]
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        run_connector = connector._Connector__run_connector

        with (
            patch("asyncio.new_event_loop") as mock_loop,
            patch("asyncio.set_event_loop"),
        ):

            # Setup mocks
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop
            connector._Connector__connect = AsyncMock()
            connector._Connector__run_loop = AsyncMock()
            connector._Connector__disconnect = AsyncMock()

            # Call the method
            run_connector()

            assert len(connector._robot_session.camera_streamers.keys()) == len(
                connector.config.cameras
            )
            assert "0" in connector._robot_session.camera_streamers.keys()
            streamer = connector._robot_session.camera_streamers["0"]
            assert streamer.camera.rate == 5
            assert streamer.camera.scaling == 0.2
            assert streamer.camera.quality == 30
            assert streamer.camera.video_url == str(base_model["cameras"][0].video_url)

    def test_stop(self, base_connector):
        base_connector._Connector__thread = MagicMock()
        base_connector._Connector__thread.is_alive.return_value = False
        assert not base_connector._Connector__stop_event.is_set()
        base_connector.stop()
        assert base_connector._Connector__stop_event.is_set()
        assert base_connector._Connector__thread.join.called

    def test_stop_raises_exception_if_thread_does_not_stop_in_time(
        self, base_connector
    ):
        base_connector._Connector__thread = MagicMock()
        assert not base_connector._Connector__stop_event.is_set()
        with pytest.raises(Exception, match="Thread did not stop in time"):
            base_connector.stop()
            assert base_connector._Connector__stop_event.is_set()
            assert base_connector._Connector__thread.join.called

    def test_run_loop(self, base_model):
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        connector._execution_loop = AsyncMock()
        connector._robot_session = Mock()
        assert not connector._Connector__stop_event.is_set()

        connector.start()
        sleep(1.0 / connector.config.update_freq)
        assert connector._Connector__loop.is_running()
        connector.stop()
        assert not connector._Connector__loop.is_running()

        connector._execution_loop.reset_mock()
        sleep((1.0 / connector.config.update_freq) * 2)
        connector._execution_loop.assert_not_called()

    def test_run_loop_catches_exceptions(self, base_model):
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        connector._execution_loop = AsyncMock(side_effect=Exception("Test exception"))
        connector._robot_session = Mock()
        connector._logger = MagicMock()

        connector.start()
        sleep(1.0 / connector.config.update_freq)
        assert connector._Connector__loop.is_running()
        connector.stop()
        assert not connector._Connector__loop.is_running()
        connector._execution_loop.assert_called()
        connector._logger.error.assert_called()

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
                "map_label": "This is a map!",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
            }
        }
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch.object(connector._robot_session, "publish_map") as mock_publish:
            connector.publish_map("frameA")
            mock_publish.assert_called_once_with(
                file=Path(f"{os.path.dirname(__file__)}/dir/test_map.png"),
                map_id="valid_map_id",
                map_label="This is a map!",
                frame_id="frameA",
                x=0.0,
                y=0.0,
                resolution=0.1,
                ts=None,
                is_update=False,
            )

    def test_publish_pose_updates_maps(self, base_model):
        base_model["maps"] = {
            "frameA": {
                "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                "map_id": "valid_map_id",
                "map_label": "This is a map!",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
            },
            # The second map has no label. The edge-sdk will treat defaults.
            "frameB": {
                "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                "map_id": "valid_map_id_b",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
            },
        }
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        with patch.object(connector._robot_session, "publish_map") as mock_publish_map:
            connector.publish_pose(0, 0, 0, "frameA")
            mock_publish_map.assert_called_once_with(
                file=Path(f"{os.path.dirname(__file__)}/dir/test_map.png"),
                map_id="valid_map_id",
                map_label="This is a map!",
                frame_id="frameA",
                x=0.0,
                y=0.0,
                resolution=0.1,
                ts=None,
                is_update=True,
            )
            mock_publish_map.reset_mock()
            connector.publish_pose(0, 0, 0, "frameA")
            mock_publish_map.assert_not_called()
            connector.publish_pose(0, 0, 0, "frameB")
            mock_publish_map.assert_called_once_with(
                file=Path(f"{os.path.dirname(__file__)}/dir/test_map.png"),
                map_id="valid_map_id_b",
                map_label=None,
                frame_id="frameB",
                x=0.0,
                y=0.0,
                resolution=0.1,
                ts=None,
                is_update=True,
            )

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

    def test_uses_env_vars(self, base_model):
        base_model["env_vars"] = {"ENV_VAR": "env_value"}
        Connector("TestRobot", InorbitConnectorConfig(**base_model))
        assert "ENV_VAR" in os.environ
        assert os.environ["ENV_VAR"] == "env_value"

    def test_resilience_config_defaults(self, base_model):
        """Test that resilience configuration has correct defaults."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))

        # Check default values
        assert connector._Connector__status_heartbeat_enabled is True
        assert connector._Connector__status_heartbeat_interval == 30.0
        assert connector._Connector__edgesdk_restart_on_timeout is True
        assert (
            connector._Connector__edgesdk_restart_timeout == 60.0
        )  # 2x heartbeat interval
        assert connector._Connector__last_successful_publish is not None
        assert connector._Connector__last_status_heartbeat is not None

    def test_resilience_config_environment_variables(self, base_model):
        """Test that resilience configuration can be set via environment variables."""
        env_vars = {
            "INORBIT_STATUS_HEARTBEAT_ENABLED": "false",
            "INORBIT_STATUS_HEARTBEAT_INTERVAL_SECONDS": "45.0",
            "INORBIT_RESTART_ON_EDGESDK_TIMEOUT": "false",
            "INORBIT_EDGESDK_RESTART_TIMEOUT_SECONDS": "120.0",
        }

        with patch.dict(os.environ, env_vars):
            connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))

            assert connector._Connector__status_heartbeat_enabled is False
            assert connector._Connector__status_heartbeat_interval == 45.0
            assert connector._Connector__edgesdk_restart_on_timeout is False
            assert connector._Connector__edgesdk_restart_timeout == 120.0

    def test_resilience_config_validation_warning(self, base_model):
        """Test that a warning is logged when restart timeout <= heartbeat interval."""
        env_vars = {
            "INORBIT_STATUS_HEARTBEAT_INTERVAL_SECONDS": "60.0",
            "INORBIT_EDGESDK_RESTART_TIMEOUT_SECONDS": "30.0",  # Less than heartbeat
        }

        with patch.dict(os.environ, env_vars):
            with patch("logging.getLogger") as mock_logger:
                mock_logger_instance = MagicMock()
                mock_logger.return_value = mock_logger_instance

                Connector("TestRobot", InorbitConnectorConfig(**base_model))

                # Should log a warning about the configuration
                mock_logger_instance.warning.assert_called()
                warning_call = mock_logger_instance.warning.call_args[0][0]
                assert "should be longer than" in warning_call
                assert "heartbeat interval" in warning_call

    def test_send_status_heartbeat_enabled(self, base_connector):
        """Test status heartbeat when enabled."""
        base_connector._robot_session = MagicMock()
        base_connector._robot_session.send_robot_status.return_value = (
            None  # Success (no exception)
        )

        # Mock time to simulate heartbeat interval passing
        with patch("time.time") as mock_time:
            # Set initial time
            mock_time.return_value = 1000.0
            base_connector._Connector__last_status_heartbeat = 970.0  # 30 seconds ago

            base_connector._send_status_heartbeat()

            # Should call send_robot_status and update timestamp
            base_connector._robot_session.send_robot_status.assert_called_once_with(
                online=True
            )
            assert base_connector._Connector__last_status_heartbeat == 1000.0

    def test_send_status_heartbeat_not_due(self, base_connector):
        """Test status heartbeat when not due yet."""
        base_connector._robot_session = MagicMock()

        # Mock time to simulate heartbeat not due
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            base_connector._Connector__last_status_heartbeat = (
                990.0  # Only 10 seconds ago
            )

            base_connector._send_status_heartbeat()

            # Should not call send_robot_status
            base_connector._robot_session.send_robot_status.assert_not_called()

    def test_send_status_heartbeat_disabled(self, base_model):
        """Test status heartbeat when disabled."""
        env_vars = {"INORBIT_STATUS_HEARTBEAT_ENABLED": "false"}

        with patch.dict(os.environ, env_vars):
            connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
            connector._robot_session = MagicMock()

            # Mock time to simulate heartbeat interval passing
            with patch("time.time") as mock_time:
                mock_time.return_value = 1000.0
                connector._Connector__last_status_heartbeat = 970.0  # 30 seconds ago

                connector._send_status_heartbeat()

                # Should not call send_robot_status when disabled
                connector._robot_session.send_robot_status.assert_not_called()

    def test_send_status_heartbeat_failure(self, base_connector):
        """Test status heartbeat when send_robot_status fails."""
        base_connector._robot_session = MagicMock()
        base_connector._robot_session.send_robot_status.side_effect = RuntimeError(
            "Failed to publish"
        )
        base_connector._logger = MagicMock()

        # Mock time to simulate heartbeat interval passing
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            base_connector._Connector__last_status_heartbeat = 970.0  # 30 seconds ago

            base_connector._send_status_heartbeat()

            # Should call send_robot_status but not update timestamp on failure
            base_connector._robot_session.send_robot_status.assert_called_once_with(
                online=True
            )
            assert (
                base_connector._Connector__last_status_heartbeat == 970.0
            )  # Unchanged
            base_connector._logger.debug.assert_called()

    def test_mark_successful_publish(self, base_connector):
        """Test marking successful publish updates timestamp."""
        with patch("time.time") as mock_time:
            mock_time.return_value = 1500.0

            base_connector._mark_successful_publish()

            assert base_connector._Connector__last_successful_publish == 1500.0

    def test_check_edgesdk_health_healthy(self, base_connector):
        """Test health check when EdgeSDK is healthy."""
        # Mock time to simulate recent successful publish
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            base_connector._Connector__last_successful_publish = 970.0  # 30 seconds ago

            # Should not exit (no exception)
            base_connector._check_edgesdk_health()

    def test_check_edgesdk_health_unhealthy_exits(self, base_connector):
        """Test health check exits when EdgeSDK is unhealthy."""
        base_connector._logger = MagicMock()

        # Mock time to simulate old successful publish (beyond timeout)
        with patch("time.time") as mock_time, patch("sys.exit") as mock_exit:
            mock_time.return_value = 1000.0
            base_connector._Connector__last_successful_publish = (
                930.0  # 70 seconds ago (> 60s timeout)
            )

            base_connector._check_edgesdk_health()

            # Should log critical error and exit
            base_connector._logger.critical.assert_called()
            mock_exit.assert_called_once_with(1)

            # Check log message content
            critical_call = base_connector._logger.critical.call_args[0][0]
            assert "EdgeSDK appears unhealthy" in critical_call
            assert "70.0s" in critical_call
            assert "timeout: 60.0s" in critical_call

    def test_check_edgesdk_health_disabled(self, base_model):
        """Test health check when disabled."""
        env_vars = {"INORBIT_RESTART_ON_EDGESDK_TIMEOUT": "false"}

        with patch.dict(os.environ, env_vars):
            connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
            connector._logger = MagicMock()

            # Mock time to simulate very old successful publish
            with patch("time.time") as mock_time, patch("sys.exit") as mock_exit:
                mock_time.return_value = 1000.0
                connector._Connector__last_successful_publish = 800.0  # 200 seconds ago

                connector._check_edgesdk_health()

                # Should not log or exit when disabled
                connector._logger.critical.assert_not_called()
                mock_exit.assert_not_called()

    def test_connect_resets_successful_publish_timestamp(self, base_connector):
        """Test that successful connection resets the successful publish timestamp."""
        base_connector._robot_session = MagicMock()
        base_connector._connect = AsyncMock()
        base_connector._logger = MagicMock()

        with patch("time.time") as mock_time:
            mock_time.return_value = 2000.0

            # Call the private __connect method
            import asyncio

            asyncio.run(base_connector._Connector__connect())

            # Should reset timestamp and log success
            assert base_connector._Connector__last_successful_publish == 2000.0
            base_connector._logger.info.assert_called_with(
                "Connected to InOrbit successfully"
            )

    def test_connect_failure_does_not_reset_timestamp(self, base_connector):
        """Test that failed connection does not reset successful publish timestamp."""
        base_connector._robot_session = MagicMock()
        base_connector._robot_session.connect.side_effect = RuntimeError(
            "Connection failed"
        )
        base_connector._connect = AsyncMock()

        original_timestamp = 1500.0
        base_connector._Connector__last_successful_publish = original_timestamp

        with pytest.raises(RuntimeError):
            import asyncio

            asyncio.run(base_connector._Connector__connect())

        # Should not reset timestamp on failure
        assert base_connector._Connector__last_successful_publish == original_timestamp


class TestConnectorCommandHandler:

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "api_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_connector_not_abstract(self):
        Connector.__abstractmethods__ = set()

    @pytest.fixture
    def base_connector(self, base_model):
        return Connector("TestRobot", InorbitConnectorConfig(**base_model))

    def test_register_command_handler(self, base_model):
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

    def test_handler_wrapper_success(self, base_connector):
        """Test the wrapper function's behavior on successful command execution."""
        connector = base_connector
        connector._robot_session = MagicMock()
        connector._Connector__loop = MagicMock()
        connector._logger = MagicMock()

        with patch("asyncio.run_coroutine_threadsafe") as mock_run_coroutine:

            mock_async_handler = AsyncMock()

            # 1. Register the handler to get the wrapper
            connector._register_custom_command_handler(mock_async_handler)
            wrapper_func = connector._robot_session.register_command_callback.call_args[
                0
            ][0]

            # 2. Prepare arguments for the commands handler
            command_name = "test_command"
            args = ["arg1", "arg2"]
            mock_result_func = MagicMock()
            options = {"result_function": mock_result_func}

            # 3. Call the wrapper
            wrapper_func(command_name, args, options)

            # 4. Assertions
            # Check that run_coroutine_threadsafe was called correctly
            mock_run_coroutine.assert_called_once()
            # Check the coroutine passed to run_coroutine_threadsafe
            assert mock_async_handler.called
            assert mock_async_handler.call_args[0] == (command_name, args, options)
            # Check the loop passed to run_coroutine_threadsafe
            assert mock_run_coroutine.call_args[0][1] is connector._Connector__loop

            # Ensure no error logs were made and result_function wasn't called by the
            # wrapper
            connector._logger.error.assert_not_called()
            mock_result_func.assert_not_called()  # The handler itself should call it

    @pytest.mark.skip(reason="Haven't been able to test the error handling")
    def test_handler_wrapper_exception(self, base_connector):
        """Test wrapper sync handler exception."""
        connector = base_connector
        connector._robot_session = MagicMock()
        connector._Connector__loop = MagicMock()

        # Mock run_coroutine_threadsafe. We only care that it's called.
        with patch("asyncio.run_coroutine_threadsafe") as mock_run_coroutine:

            mock_async_handler = AsyncMock()
            mock_exception = Exception("Test exception")

            # Configure the handler to raise immediately upon call
            mock_async_handler.side_effect = mock_exception

            # 1. Register the handler to get the wrapper
            connector._register_custom_command_handler(mock_async_handler)
            wrapper_func = connector._robot_session.register_command_callback.call_args[
                0
            ][0]

            # 2. Prepare arguments for the wrapper
            cmd_name = "test_command"
            args = ["arg1", "arg2"]
            mock_result_func = MagicMock()
            options = {"result_function": mock_result_func}

            # 3. Call the wrapper
            wrapper_func(cmd_name, args, options)

            # 4. Assertions: Check only the essentials before exception likely halts
            # flow
            # Check run_coroutine_threadsafe was called
            mock_run_coroutine.assert_called_once()
            # Check the handler itself was called (which triggered the side_effect)
            mock_async_handler.assert_called()  # Check it was called at least
