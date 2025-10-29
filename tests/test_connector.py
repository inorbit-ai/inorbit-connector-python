#!/usr/bin/env python
# -*- coding: utf-8 -*-
# License: MIT License
# Copyright 2024 InOrbit, Inc.

# Standard
import os
from time import sleep
from unittest.mock import AsyncMock, MagicMock, patch

# Third-party
import pytest
from pydantic import AnyHttpUrl, BaseModel
from inorbit_edge.robot import RobotSession

# InOrbit
from inorbit_connector.connector import (
    Connector,
    FleetConnector,
    InorbitConnectorConfig,
)


class DummyConfig(BaseModel):
    pass


# ==============================================================================
# Test Fixtures and Helpers
# ==============================================================================


@pytest.fixture(autouse=True)
def mock_robot_session_pool():
    """Mock RobotSessionPool to prevent automatic connections during tests.

    This is autouse=True so it applies to all tests automatically.
    """
    with patch("inorbit_connector.connector.RobotSessionPool") as mock_pool_class:
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        # Dictionary to cache mock sessions per robot_id
        sessions_cache = {}

        # Create a function that returns the same mock session for each robot_id
        def get_session_side_effect(robot_id, robot_name=None):
            if robot_id not in sessions_cache:
                mock_session = MagicMock(spec=RobotSession)
                mock_session.robot_id = robot_id
                mock_session.robot_name = robot_name or robot_id
                mock_session.robot_key = None
                mock_session.api_key = "valid_key"
                mock_session.robot_api_key = None
                mock_session.endpoint = "https://valid.com/"
                mock_session.use_ssl = True
                mock_session.use_websockets = False
                mock_session.camera_streamers = {}
                mock_session._online_status_callback = None
                sessions_cache[robot_id] = mock_session
            return sessions_cache[robot_id]

        mock_pool.get_session.side_effect = get_session_side_effect

        yield mock_pool


# ==============================================================================
# FleetConnector Tests
# ==============================================================================


class TestFleetConnectorIsAbstract:
    def test_fleet_connector_is_abstract(self):
        assert FleetConnector.__abstractmethods__ == {
            "_connect",
            "_disconnect",
            "_execution_loop",
            "_inorbit_robot_command_handler",
        }

    def test_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            FleetConnector(["TestRobot1", "TestRobot2"], MagicMock())

    def test_cannot_be_subclassed_without_overriding_abstract_methods(self):

        class SubFleetConnector(FleetConnector):
            pass

        with pytest.raises(TypeError):
            SubFleetConnector(["TestRobot1", "TestRobot2"], MagicMock())

    def test_can_be_subclassed_with_all_abstract_methods_implemented(self):

        class SubFleetConnector(FleetConnector):
            async def _connect(self):
                pass

            async def _disconnect(self):
                pass

            async def _execution_loop(self):
                pass

            async def _inorbit_robot_command_handler(
                self, robot_id, command_name, args, options
            ):
                pass

        connector = SubFleetConnector(
            ["TestRobot1", "TestRobot2"],
            InorbitConnectorConfig(
                api_key="valid_key",
                api_url="https://valid.com/",
                connector_type="valid_connector",
                connector_config=DummyConfig(),
            ),
        )
        assert isinstance(connector, FleetConnector)


class TestFleetConnector:

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "api_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_fleet_connector_not_abstract(self):
        FleetConnector.__abstractmethods__ = set()

    @pytest.fixture
    def base_fleet_connector(self, base_model):
        return FleetConnector(
            ["TestRobot1", "TestRobot2"], InorbitConnectorConfig(**base_model)
        )

    def test_init(self, base_model):
        config = InorbitConnectorConfig(**base_model)
        robot_ids = ["TestRobot1", "TestRobot2"]

        connector = FleetConnector(robot_ids, config)
        assert connector.robot_ids == robot_ids
        assert connector.config == config
        assert connector._logger.name == FleetConnector.__module__

    def test_init_with_robot_key(self, base_model):
        config = InorbitConnectorConfig(
            **base_model, inorbit_robot_key="valid_robot_key"
        )
        robot_ids = ["TestRobot1", "TestRobot2"]

        connector = FleetConnector(robot_ids, config)
        # Fleet connector should configure the session factory with robot_key

    def test_get_robot_session(self, base_fleet_connector, mock_robot_session_pool):
        """Test that _get_robot_session returns a session for a specific robot."""
        robot_id = "TestRobot1"
        session = base_fleet_connector._get_robot_session(robot_id)
        assert session is not None
        assert session.robot_id == robot_id
        mock_robot_session_pool.get_session.assert_called()

    def test_publish_robot_pose(self, base_fleet_connector, mock_robot_session_pool):
        """Test publishing pose for a specific robot."""
        robot_id = "TestRobot1"
        base_fleet_connector.publish_robot_pose(robot_id, 1.0, 2.0, 3.14, "map1")

        # Verify get_session was called and get the actual session returned
        mock_robot_session_pool.get_session.assert_called_with(robot_id)
        # Get the session from the side_effect cache
        session = base_fleet_connector._get_robot_session(robot_id)
        session.publish_pose.assert_called()

    def test_publish_robot_pose_updates_map(self, base_model, mock_robot_session_pool):
        """Test that publishing pose with new frame_id updates the map."""
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
        connector = FleetConnector(["TestRobot1"], InorbitConnectorConfig(**base_model))

        connector.publish_robot_pose("TestRobot1", 0, 0, 0, "frameA")

        # Get the actual session that was created
        session = connector._get_robot_session("TestRobot1")
        session.publish_map.assert_called_once()
        session.publish_pose.assert_called_once()

    def test_publish_robot_odometry(
        self, base_fleet_connector, mock_robot_session_pool
    ):
        """Test publishing odometry for a specific robot."""
        robot_id = "TestRobot1"
        base_fleet_connector.publish_robot_odometry(
            robot_id, linear_speed=1.0, angular_speed=0.5
        )
        session = base_fleet_connector._get_robot_session(robot_id)
        session.publish_odometry.assert_called()

    def test_publish_robot_key_values(
        self, base_fleet_connector, mock_robot_session_pool
    ):
        """Test publishing key values for a specific robot."""
        robot_id = "TestRobot1"
        base_fleet_connector.publish_robot_key_values(
            robot_id, key1="value1", key2="value2"
        )
        session = base_fleet_connector._get_robot_session(robot_id)
        session.publish_key_values.assert_called()

    def test_publish_robot_system_stats(
        self, base_fleet_connector, mock_robot_session_pool
    ):
        """Test publishing system stats for a specific robot."""
        robot_id = "TestRobot1"
        base_fleet_connector.publish_robot_system_stats(
            robot_id, cpu_load_percentage=50.0
        )
        session = base_fleet_connector._get_robot_session(robot_id)
        session.publish_system_stats.assert_called()

    def test_is_fleet_robot_online_default(self, base_fleet_connector):
        """Test that _is_fleet_robot_online returns True by default."""
        assert base_fleet_connector._is_fleet_robot_online("TestRobot1") is True

    @pytest.mark.asyncio
    async def test_register_user_scripts(
        self, base_model, tmp_path, mock_robot_session_pool
    ):
        """Test user scripts registration for fleet connector."""
        # Create a connector with user scripts enabled
        connector = FleetConnector(
            ["TestRobot1", "TestRobot2"],
            InorbitConnectorConfig(**base_model),
            register_user_scripts=True,
            default_user_scripts_dir=tmp_path,
        )
        connector._connect = AsyncMock()

        # Initialize sessions (this is what happens during start/connect)
        await connector._FleetConnector__connect()

        # Verify register_commands_path was called for each robot
        session_r1 = connector._get_robot_session("TestRobot1")
        session_r2 = connector._get_robot_session("TestRobot2")
        session_r1.register_commands_path.assert_called_once()
        session_r2.register_commands_path.assert_called_once()

    def test_uses_env_vars(self, base_model):
        base_model["env_vars"] = {"FLEET_ENV_VAR": "fleet_value"}
        FleetConnector(["TestRobot1"], InorbitConnectorConfig(**base_model))
        assert "FLEET_ENV_VAR" in os.environ
        assert os.environ["FLEET_ENV_VAR"] == "fleet_value"


# ==============================================================================
# Connector Tests (Single Robot - Subclass of FleetConnector)
# ==============================================================================


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
            async def _connect(self):
                pass

            async def _disconnect(self):
                pass

            async def _execution_loop(self):
                pass

            async def _inorbit_command_handler(self, command_name, args, options):
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
        assert isinstance(connector, FleetConnector)  # Connector is a FleetConnector


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
        assert connector.robot_ids == [robot_id]  # Single robot wrapped in list
        assert connector.config == config
        assert connector._logger.name == Connector.__module__

    def test_init_with_robot_key(self, base_model, mock_robot_session_pool):
        config = InorbitConnectorConfig(
            **base_model, inorbit_robot_key="valid_robot_key"
        )
        robot_id = "TestRobot"

        connector = Connector(robot_id, config)
        # Session is created on-demand, check when accessed
        session = connector._get_session()
        assert session.robot_id == "TestRobot"

    def test_get_session(self, base_connector, mock_robot_session_pool):
        """Test that _get_session returns the session for the single robot."""
        session = base_connector._get_session()
        assert session is not None
        assert session.robot_id == "TestRobot"
        mock_robot_session_pool.get_session.assert_called()

    def test_publish_map(self, base_model, mock_robot_session_pool):
        """Test publish_map delegates to FleetConnector.publish_robot_map."""
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

        connector.publish_map("frameA")

        session = connector._get_session()
        session.publish_map.assert_called_once()

    def test_publish_pose(self, base_model, mock_robot_session_pool):
        """Test publish_pose delegates to FleetConnector.publish_robot_pose."""
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

        connector.publish_pose(1.0, 2.0, 3.14, "frameA")

        session = connector._get_session()
        session.publish_pose.assert_called()

    def test_publish_pose_updates_maps(self, base_model, mock_robot_session_pool):
        """Test that publishing pose with new frame_id updates the map."""
        base_model["maps"] = {
            "frameA": {
                "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                "map_id": "valid_map_id",
                "map_label": "This is a map!",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
            },
            "frameB": {
                "file": f"{os.path.dirname(__file__)}/dir/test_map.png",
                "map_id": "valid_map_id_b",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "resolution": 0.1,
            },
        }
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))

        session = connector._get_session()

        connector.publish_pose(0, 0, 0, "frameA")
        assert session.publish_map.call_count == 1
        assert session.publish_pose.call_count == 1

        # Second pose to same frame should not update map
        connector.publish_pose(0, 0, 0, "frameA")
        assert session.publish_map.call_count == 1  # Still 1
        assert session.publish_pose.call_count == 2  # Now 2

        # Change to different frame should update map
        connector.publish_pose(0, 0, 0, "frameB")
        assert session.publish_map.call_count == 2  # Now 2
        assert session.publish_pose.call_count == 3  # Now 3

    def test_publish_odometry(self, base_connector, mock_robot_session_pool):
        """Test publish_odometry delegates correctly."""
        base_connector.publish_odometry(linear_speed=1.0, angular_speed=0.5)

        session = base_connector._get_session()
        session.publish_odometry.assert_called()

    def test_publish_key_values(self, base_connector, mock_robot_session_pool):
        """Test publish_key_values delegates correctly."""
        base_connector.publish_key_values(key1="value1")

        session = base_connector._get_session()
        session.publish_key_values.assert_called()

    def test_publish_system_stats(self, base_connector, mock_robot_session_pool):
        """Test publish_system_stats delegates correctly."""
        base_connector.publish_system_stats(cpu_load_percentage=50.0)

        session = base_connector._get_session()
        session.publish_system_stats.assert_called()

    def test_is_robot_online_default_implementation(self, base_connector):
        """Test that _is_robot_online returns True by default."""
        assert base_connector._is_robot_online() is True

    def test_is_fleet_robot_online_delegates_to_is_robot_online(self, base_connector):
        """Test that _is_fleet_robot_online delegates to _is_robot_online."""
        assert base_connector._is_fleet_robot_online("TestRobot") is True

    @pytest.mark.asyncio
    async def test_inorbit_robot_command_handler_delegates(self, base_connector):
        """Test that _inorbit_robot_command_handler delegates to _inorbit_command_handler."""
        base_connector._inorbit_command_handler = AsyncMock()

        await base_connector._inorbit_robot_command_handler(
            "TestRobot", "test_cmd", ["arg1"], {"opt": "val"}
        )

        base_connector._inorbit_command_handler.assert_called_once_with(
            "test_cmd", ["arg1"], {"opt": "val"}
        )

    @pytest.mark.asyncio
    async def test_register_user_scripts(
        self, base_model, tmp_path, mock_robot_session_pool
    ):
        """Test user scripts registration for single robot connector."""
        # Create a connector with user scripts enabled
        connector = Connector(
            "TestRobot",
            InorbitConnectorConfig(**base_model),
            register_user_scripts=True,
            default_user_scripts_dir=tmp_path,
        )
        connector._connect = AsyncMock()

        # Initialize sessions (this is what happens during start/connect)
        await connector._FleetConnector__connect()

        # Verify register_commands_path was called
        session = connector._get_session()
        session.register_commands_path.assert_called_once()

    def test_uses_env_vars(self, base_model):
        base_model["env_vars"] = {"ENV_VAR": "env_value"}
        Connector("TestRobot", InorbitConnectorConfig(**base_model))
        assert "ENV_VAR" in os.environ
        assert os.environ["ENV_VAR"] == "env_value"

    @pytest.mark.asyncio
    async def test_start_stop_integration(self, base_model):
        """Integration test for start/stop functionality."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        connector._execution_loop = AsyncMock()
        connector._connect = AsyncMock()
        connector._disconnect = AsyncMock()

        connector.start()
        sleep(0.5)
        assert connector._FleetConnector__loop.is_running()

        connector.stop()
        assert not connector._FleetConnector__loop.is_running()


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

    @pytest.mark.asyncio
    async def test_register_command_handler_by_default(
        self, base_model, mock_robot_session_pool
    ):
        """Test that command handler is registered by default."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        connector._connect = AsyncMock()

        # Initialize sessions (this triggers command handler registration)
        await connector._FleetConnector__connect()

        # Verify register_command_callback was called
        session = connector._get_session()
        session.register_command_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_register_when_disabled(
        self, base_model, mock_robot_session_pool
    ):
        """Test that command handler is not registered when disabled."""
        connector = Connector(
            "TestRobot",
            InorbitConnectorConfig(**base_model),
            register_custom_command_handler=False,
        )
        connector._connect = AsyncMock()

        # Initialize sessions
        await connector._FleetConnector__connect()

        # Verify register_command_callback was NOT called
        session = connector._get_session()
        session.register_command_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_sets_online_status_callback(
        self, base_model, mock_robot_session_pool
    ):
        """Test that online status callback is set on EdgeSDK."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        connector._connect = AsyncMock()

        # Initialize sessions
        await connector._FleetConnector__connect()

        # Verify callback was set
        session = connector._get_session()
        session.set_online_status_callback.assert_called_once()

        # Verify the callback calls _is_robot_online
        callback = session.set_online_status_callback.call_args[0][0]
        assert callback() is True  # Should return True by default
