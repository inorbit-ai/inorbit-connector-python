#!/usr/bin/env python

# Copyright 2024 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Standard
import logging
import os
import threading
from contextlib import contextmanager
from time import sleep
from unittest.mock import AsyncMock, MagicMock, patch

# Third-party
import pytest
from pydantic import AnyHttpUrl
from inorbit_edge.models import CameraConfig
from inorbit_edge.robot import RobotSession
from inorbit_edge.video import OpenCVCamera

# InOrbit
from inorbit_connector.connector import (
    CommandFailure,
    CommandResultCode,
    Connector,
    FleetConnector,
)
from inorbit_connector.models import (
    ConnectorRootConfig,
    ConnectorSpecificConfig,
    RobotConfig,
)


class DummyConfig(ConnectorSpecificConfig):
    CONNECTOR_TYPE = "valid_connector"


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


def _seed_sessions(connector):
    """Mimic the post-``__connect()`` state for tests that don't call ``start()``.

    Production creates the per-robot sessions in ``__connect()``; tests that build a
    connector directly must seed ``__robot_sessions`` so the ``publish_*`` /
    ``_get_robot_session`` paths (which read the connector's own session map) work.
    """
    pool = connector._FleetConnector__session_pool
    connector._FleetConnector__robot_sessions = {
        rc.robot_id: pool.get_session(rc.robot_id, robot_name=rc.robot_id)
        for rc in connector.config.fleet
    }
    return connector


@contextmanager
def _concrete(cls):
    """Temporarily clear ``cls.__abstractmethods__`` so it can be instantiated.

    Restores the original set on exit so the change does not leak between tests.
    """
    saved = cls.__abstractmethods__
    cls.__abstractmethods__ = frozenset()
    try:
        yield
    finally:
        cls.__abstractmethods__ = saved


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
            FleetConnector(MagicMock())

    def test_cannot_be_subclassed_without_overriding_abstract_methods(self):

        class SubFleetConnector(FleetConnector):
            pass

        with pytest.raises(TypeError):
            SubFleetConnector(MagicMock())

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
            ConnectorRootConfig(
                api_key="valid_key",
                connection_config_url="https://valid.com/",
                connector_type="valid_connector",
                connector_config=DummyConfig(),
                fleet=[
                    RobotConfig(robot_id="TestRobot1"),
                    RobotConfig(robot_id="TestRobot2"),
                ],
            ),
        )
        assert isinstance(connector, FleetConnector)


class TestFleetConnector:

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "connection_config_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_fleet_connector_not_abstract(self):
        with _concrete(FleetConnector):
            yield

    @pytest.fixture
    def base_fleet_connector(self, base_model):
        return _seed_sessions(
            FleetConnector(
                ConnectorRootConfig(
                    **base_model,
                    fleet=[
                        RobotConfig(robot_id="TestRobot1"),
                        RobotConfig(robot_id="TestRobot2"),
                    ],
                )
            )
        )

    def test_init(self, base_model):
        config = ConnectorRootConfig(
            **base_model,
            fleet=[
                RobotConfig(robot_id="TestRobot1"),
                RobotConfig(robot_id="TestRobot2"),
            ],
        )
        robot_ids = ["TestRobot1", "TestRobot2"]

        connector = FleetConnector(config)
        assert connector.robot_ids == robot_ids
        assert connector.config == config
        assert connector._logger.name == FleetConnector.__module__

    def test_init_with_robot_key(self, base_model):
        config = ConnectorRootConfig(
            **base_model,
            inorbit_robot_key="valid_robot_key",
            fleet=[
                RobotConfig(robot_id="TestRobot1"),
                RobotConfig(robot_id="TestRobot2"),
            ],
        )
        robot_ids = ["TestRobot1", "TestRobot2"]

        connector = FleetConnector(config)
        assert connector.robot_ids == robot_ids
        assert connector.config.inorbit_robot_key == "valid_robot_key"
        assert connector.config.api_key == "valid_key"

        # Access the private session factory using name mangling
        session_factory = connector._FleetConnector__session_factory
        # The factory should have been initialized with the config values
        # RobotSessionFactory stores kwargs in robot_session_kw_args
        assert session_factory.robot_session_kw_args["robot_key"] == "valid_robot_key"
        assert session_factory.robot_session_kw_args["api_key"] == "valid_key"
        assert (
            str(session_factory.robot_session_kw_args["endpoint"])
            == "https://valid.com/"
        )

    def test_get_robot_session(self, base_fleet_connector, mock_robot_session_pool):
        """Test that _get_robot_session returns a session for a specific robot."""
        robot_id = "TestRobot1"
        session = base_fleet_connector._get_robot_session(robot_id)
        assert session is not None
        assert session.robot_id == robot_id
        mock_robot_session_pool.get_session.assert_called()

    def test_use_websockets_defaults_false_in_factory(self, base_fleet_connector):
        """By default the session factory should request the TCP transport."""
        session_factory = base_fleet_connector._FleetConnector__session_factory
        assert session_factory.robot_session_kw_args["use_websockets"] is False

    def test_use_websockets_propagates_to_factory(self, base_model):
        """When use_websockets=True is set on the config, it must reach the
        RobotSessionFactory so the edge-sdk RobotSession picks the websockets
        (wss when use_ssl is on) transport."""
        config = ConnectorRootConfig(
            **base_model,
            use_websockets=True,
            fleet=[
                RobotConfig(robot_id="TestRobot1"),
                RobotConfig(robot_id="TestRobot2"),
            ],
        )
        connector = FleetConnector(config)
        session_factory = connector._FleetConnector__session_factory
        assert session_factory.robot_session_kw_args["use_websockets"] is True

    def test_publish_robot_pose(self, base_fleet_connector, mock_robot_session_pool):
        """Test publishing pose for a specific robot."""
        robot_id = "TestRobot1"
        base_fleet_connector.publish_robot_pose(robot_id, 1.0, 2.0, 3.14, "map1")

        # The robot's active session received the pose.
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
        connector = _seed_sessions(
            FleetConnector(
                ConnectorRootConfig(
                    **base_model,
                    fleet=[RobotConfig(robot_id="TestRobot1")],
                )
            )
        )

        connector.publish_robot_pose("TestRobot1", 0, 0, 0, "frameA")

        # Get the actual session that was created
        session = connector._get_robot_session("TestRobot1")
        session.publish_map.assert_called_once()
        session.publish_pose.assert_called_once()

    def test_publish_robot_pose_no_map_logs_once(
        self, base_fleet_connector, mock_robot_session_pool
    ):
        """Test that pose with unknown frame_id only triggers map update once."""
        robot_id = "TestRobot1"
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        base_fleet_connector._FleetConnector__loop = mock_loop

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            base_fleet_connector.publish_robot_pose(
                robot_id, 1.0, 2.0, 0.0, "unknown_frame"
            )
            base_fleet_connector.publish_robot_pose(
                robot_id, 3.0, 4.0, 0.0, "unknown_frame"
            )

        session = base_fleet_connector._get_robot_session(robot_id)
        # publish_map never called (map not in config)
        session.publish_map.assert_not_called()
        # publish_pose called both times
        assert session.publish_pose.call_count == 2
        # mock_run never scheduled the coroutine(s) — close them so GC
        # doesn't surface "coroutine was never awaited" later.
        for call in mock_run.call_args_list:
            call[0][0].close()

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

    def test_publish_robot_key_values_injects_connector_type(
        self, base_fleet_connector, mock_robot_session_pool
    ):
        """publish_robot_key_values injects connector_type automatically."""
        robot_id = "TestRobot1"
        base_fleet_connector.publish_robot_key_values(robot_id, foo="bar")
        session = base_fleet_connector._get_robot_session(robot_id)
        session.publish_key_values.assert_called_with(
            {"connector_type": DummyConfig.CONNECTOR_TYPE, "foo": "bar"}
        )

    def test_publish_robot_key_values_connector_type_overridable(
        self, base_fleet_connector, mock_robot_session_pool
    ):
        """Subclass can override connector_type via kwargs."""
        robot_id = "TestRobot1"
        base_fleet_connector.publish_robot_key_values(robot_id, connector_type="custom")
        session = base_fleet_connector._get_robot_session(robot_id)
        session.publish_key_values.assert_called_with({"connector_type": "custom"})

    def test_publish_robot_system_stats_stores_stats(
        self, base_fleet_connector, mock_robot_session_pool
    ):
        """Test that publish_robot_system_stats stores stats instead of publishing."""
        robot_id = "TestRobot1"
        base_fleet_connector.publish_robot_system_stats(
            robot_id, cpu_load_percentage=0.5
        )
        # Stats should be stored, not published immediately
        session = base_fleet_connector._get_robot_session(robot_id)
        session.publish_system_stats.assert_not_called()
        # Verify stats were stored
        pending_stats = base_fleet_connector._FleetConnector__pending_system_stats
        assert robot_id in pending_stats
        assert pending_stats[robot_id]["cpu_load_percentage"] == 0.5

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
            ConnectorRootConfig(
                **base_model,
                fleet=[
                    RobotConfig(robot_id="TestRobot1"),
                    RobotConfig(robot_id="TestRobot2"),
                ],
            ),
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
        FleetConnector(
            ConnectorRootConfig(
                **base_model,
                fleet=[RobotConfig(robot_id="TestRobot1")],
            )
        )
        assert "FLEET_ENV_VAR" in os.environ
        assert os.environ["FLEET_ENV_VAR"] == "fleet_value"


class TestFleetConnectorMapFetching:
    """Tests for FleetConnector map fetching functionality."""

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "connection_config_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_fleet_connector_not_abstract(self):
        with _concrete(FleetConnector):
            yield

    @pytest.fixture
    def fleet_connector(self, base_model):
        return _seed_sessions(
            FleetConnector(
                ConnectorRootConfig(
                    **base_model,
                    fleet=[RobotConfig(robot_id="TestRobot1")],
                )
            )
        )

    @pytest.mark.asyncio
    async def test_fetch_robot_map_default_returns_none(self, fleet_connector):
        """Test that default fetch_robot_map returns None."""
        result = await fleet_connector.fetch_robot_map("TestRobot1", "frame1")
        assert result is None

    def test_publish_robot_map_schedules_fetch_when_map_not_found(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that publish_robot_map schedules async fetch when map not in config."""
        # Mock the event loop
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        fleet_connector._FleetConnector__loop = mock_loop

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            fleet_connector.publish_robot_map("TestRobot1", "unknown_frame")

            # Verify async fetch was scheduled
            mock_run.assert_called_once()
            # Verify the frame was added to pending fetches
            assert "unknown_frame" in (
                fleet_connector._FleetConnector__pending_map_fetches
            )
            # mock_run swallowed the coroutine without scheduling it on a
            # real loop; close it so the GC doesn't surface an
            # "coroutine was never awaited" warning later.
            mock_run.call_args[0][0].close()

    def test_schedule_map_fetch_avoids_duplicates(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that duplicate map fetch requests are ignored."""
        # Mock the event loop
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        fleet_connector._FleetConnector__loop = mock_loop

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            # First request should schedule
            fleet_connector._schedule_map_fetch("TestRobot1", "frame1", False)
            assert mock_run.call_count == 1

            # Second request for same frame should be ignored
            fleet_connector._schedule_map_fetch("TestRobot1", "frame1", False)
            assert mock_run.call_count == 1  # Still 1, not 2

            # mock_run never scheduled the coroutine; close it explicitly.
            mock_run.call_args_list[0][0][0].close()

    def test_schedule_map_fetch_requires_running_loop(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that map fetch is not scheduled if loop is not running."""
        # No loop set
        fleet_connector._FleetConnector__loop = None

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            fleet_connector._schedule_map_fetch("TestRobot1", "frame1", False)
            mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_and_publish_map_adds_to_config(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that fetched map is added to config and published."""
        from inorbit_connector.models import MapConfigTemp

        # Create a mock map response
        test_image = b"\x89PNG\r\n\x1a\ntest_image_data"
        mock_map = MapConfigTemp(
            image=test_image,
            map_id="fetched_map",
            origin_x=0.0,
            origin_y=0.0,
            resolution=0.05,
        )

        # Mock fetch_robot_map to return the map
        fleet_connector.fetch_robot_map = AsyncMock(return_value=mock_map)

        # Add frame to pending (simulating it was scheduled)
        fleet_connector._FleetConnector__pending_map_fetches.add("frame1")

        # Run the fetch and publish
        await fleet_connector._fetch_and_publish_map("TestRobot1", "frame1", False)

        # Verify map was added to config
        assert "frame1" in fleet_connector.config.maps
        assert fleet_connector.config.maps["frame1"].map_id == "fetched_map"

        # Verify frame was removed from pending
        assert "frame1" not in fleet_connector._FleetConnector__pending_map_fetches

    @pytest.mark.asyncio
    async def test_fetch_and_publish_map_handles_none(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test graceful handling when fetch returns None."""
        # Mock fetch_robot_map to return None
        fleet_connector.fetch_robot_map = AsyncMock(return_value=None)

        # Add frame to pending
        fleet_connector._FleetConnector__pending_map_fetches.add("frame1")

        # Run the fetch and publish
        await fleet_connector._fetch_and_publish_map("TestRobot1", "frame1", False)

        # Verify map was NOT added to config
        assert "frame1" not in fleet_connector.config.maps

        # Verify frame was removed from pending (cleanup still happens)
        assert "frame1" not in fleet_connector._FleetConnector__pending_map_fetches

    def test_temp_map_dir_created_lazily(self, fleet_connector):
        """Test that temp directory is only created on first use."""
        # Initially no temp dir
        assert fleet_connector._FleetConnector__temp_map_dir is None

        # Access the temp dir
        temp_dir = fleet_connector._get_temp_map_dir()

        # Now it should exist
        assert fleet_connector._FleetConnector__temp_map_dir is not None
        assert temp_dir.exists()

        # Cleanup
        fleet_connector._FleetConnector__temp_map_dir.cleanup()

    @pytest.mark.asyncio
    async def test_temp_map_dir_cleanup_on_disconnect(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that temp files are cleaned up on disconnect."""
        # Create a temp dir by accessing it
        temp_dir = fleet_connector._get_temp_map_dir()
        assert temp_dir.exists()

        # Write a test file
        test_file = temp_dir / "test.png"
        test_file.write_bytes(b"test")
        assert test_file.exists()

        # Mock _disconnect to avoid actual disconnection logic
        fleet_connector._disconnect = AsyncMock()

        # Call disconnect
        await fleet_connector._FleetConnector__disconnect()

        # Verify temp dir was cleaned up
        assert fleet_connector._FleetConnector__temp_map_dir is None
        assert not temp_dir.exists()


class TestFleetConnectorDeferredSystemStats:
    """Tests for FleetConnector deferred system stats publishing."""

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "connection_config_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_fleet_connector_not_abstract(self):
        with _concrete(FleetConnector):
            yield

    @pytest.fixture
    def fleet_connector(self, base_model, mock_robot_session_pool):
        connector = FleetConnector(
            ConnectorRootConfig(
                **base_model,
                fleet=[
                    RobotConfig(robot_id="TestRobot1"),
                    RobotConfig(robot_id="TestRobot2"),
                ],
            )
        )
        # Seed the post-connect state (sessions are created in __connect()).
        return _seed_sessions(connector)

    def test_publish_pending_system_stats_publishes_stored_stats(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that stored stats are published for robots that provided them."""
        # Store stats for TestRobot1
        fleet_connector.publish_robot_system_stats(
            "TestRobot1",
            cpu_load_percentage=0.5,
            ram_usage_percentage=0.6,
            hdd_usage_percentage=0.7,
        )

        # Call the publish method
        fleet_connector._FleetConnector__publish_pending_system_stats()

        # Verify stored stats were published for TestRobot1
        session1 = fleet_connector._get_robot_session("TestRobot1")
        session1.publish_system_stats.assert_called_once_with(
            cpu_load_percentage=0.5,
            ram_usage_percentage=0.6,
            hdd_usage_percentage=0.7,
        )

    def test_publish_pending_system_stats_publishes_zeroed_defaults(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that zeroed defaults are published for robots without stored stats."""
        # Don't store any stats, just call publish
        fleet_connector._FleetConnector__publish_pending_system_stats()

        # Verify zeroed defaults were published for both robots
        session1 = fleet_connector._get_robot_session("TestRobot1")
        session2 = fleet_connector._get_robot_session("TestRobot2")

        session1.publish_system_stats.assert_called_once_with(
            cpu_load_percentage=0.0,
            ram_usage_percentage=0.0,
            hdd_usage_percentage=0.0,
        )
        session2.publish_system_stats.assert_called_once_with(
            cpu_load_percentage=0.0,
            ram_usage_percentage=0.0,
            hdd_usage_percentage=0.0,
        )

    def test_publish_pending_system_stats_clears_stored_stats(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that stored stats are cleared after publishing."""
        fleet_connector.publish_robot_system_stats(
            "TestRobot1", cpu_load_percentage=0.5
        )
        assert "TestRobot1" in fleet_connector._FleetConnector__pending_system_stats

        fleet_connector._FleetConnector__publish_pending_system_stats()

        # Verify stats were cleared
        assert len(fleet_connector._FleetConnector__pending_system_stats) == 0

    def test_publish_pending_system_stats_mixed_stored_and_default(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that stored stats are used for some robots, defaults for others."""
        # Store stats only for TestRobot1
        fleet_connector.publish_robot_system_stats(
            "TestRobot1",
            cpu_load_percentage=0.8,
            ram_usage_percentage=0.9,
            hdd_usage_percentage=0.1,
        )

        fleet_connector._FleetConnector__publish_pending_system_stats()

        # TestRobot1 should have stored stats
        session1 = fleet_connector._get_robot_session("TestRobot1")
        session1.publish_system_stats.assert_called_once_with(
            cpu_load_percentage=0.8,
            ram_usage_percentage=0.9,
            hdd_usage_percentage=0.1,
        )

        # TestRobot2 should have zeroed defaults
        session2 = fleet_connector._get_robot_session("TestRobot2")
        session2.publish_system_stats.assert_called_once_with(
            cpu_load_percentage=0.0,
            ram_usage_percentage=0.0,
            hdd_usage_percentage=0.0,
        )

    def test_publish_connector_system_stats_uses_psutil(
        self, base_model, mock_robot_session_pool
    ):
        """Test that connector host stats are used when enabled and psutil available."""
        with patch("inorbit_connector.connector.PSUTIL_AVAILABLE", True):
            with patch("inorbit_connector.connector.psutil") as mock_psutil:
                # Mock psutil functions
                mock_psutil.cpu_percent.return_value = 50.0
                mock_psutil.virtual_memory.return_value.percent = 60.0
                mock_psutil.disk_usage.return_value.percent = 70.0

                connector = FleetConnector(
                    ConnectorRootConfig(
                        **base_model,
                        fleet=[RobotConfig(robot_id="TestRobot1")],
                    ),
                    publish_connector_system_stats=True,
                )
                # Seed the post-connect state (sessions created in __connect()).
                _seed_sessions(connector)

                connector._FleetConnector__publish_pending_system_stats()

                session = connector._get_robot_session("TestRobot1")
                session.publish_system_stats.assert_called_once_with(
                    cpu_load_percentage=0.5,  # 50.0 / 100.0
                    ram_usage_percentage=0.6,  # 60.0 / 100.0
                    hdd_usage_percentage=0.7,  # 70.0 / 100.0
                )

    def test_publish_connector_system_stats_fallback_without_psutil(
        self, base_model, mock_robot_session_pool
    ):
        """Test fallback to zeroed defaults when psutil not available."""
        with patch("inorbit_connector.connector.PSUTIL_AVAILABLE", False):
            connector = FleetConnector(
                ConnectorRootConfig(
                    **base_model,
                    fleet=[RobotConfig(robot_id="TestRobot1")],
                ),
                publish_connector_system_stats=True,
            )
            # Seed the post-connect state (sessions created in __connect()).
            _seed_sessions(connector)

            # Should have fallen back to False
            assert connector._FleetConnector__publish_connector_system_stats is False

            connector._FleetConnector__publish_pending_system_stats()

            # Should use zeroed defaults
            session = connector._get_robot_session("TestRobot1")
            session.publish_system_stats.assert_called_once_with(
                cpu_load_percentage=0.0,
                ram_usage_percentage=0.0,
                hdd_usage_percentage=0.0,
            )

    def test_publish_connector_system_stats_logs_warning_without_psutil(
        self, base_model, mock_robot_session_pool
    ):
        """Test that warning is logged when psutil not available but feature enabled."""
        with patch("inorbit_connector.connector.PSUTIL_AVAILABLE", False):
            with patch("inorbit_connector.connector.logging") as mock_logging:
                mock_logger = MagicMock()
                mock_logging.getLogger.return_value = mock_logger

                FleetConnector(
                    ConnectorRootConfig(
                        **base_model,
                        fleet=[RobotConfig(robot_id="TestRobot1")],
                    ),
                    publish_connector_system_stats=True,
                )

                # Verify warning was logged
                mock_logger.warning.assert_called()
                warning_msg = mock_logger.warning.call_args[0][0]
                assert "psutil" in warning_msg
                assert "inorbit-connector[system-stats]" in warning_msg

    def test_publish_connector_system_stats_disabled_by_default(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Test that connector system stats are disabled by default."""
        assert fleet_connector._FleetConnector__publish_connector_system_stats is False


class TestFleetConnectorRuntimeFleet:
    """Tests for runtime fleet add/remove (autodiscovery support)."""

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "connection_config_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_fleet_connector_not_abstract(self):
        with _concrete(FleetConnector):
            yield

    @pytest.fixture
    def fleet_connector(self, base_model, mock_robot_session_pool):
        """A connector in the post-connect state (sessions created for the fleet)."""
        connector = FleetConnector(
            ConnectorRootConfig(
                **base_model,
                fleet=[
                    RobotConfig(robot_id="TestRobot1"),
                    RobotConfig(robot_id="TestRobot2"),
                ],
            )
        )
        # Seed the state after __connect() created the sessions.
        return _seed_sessions(connector)

    @staticmethod
    def _sessions(connector):
        return connector._FleetConnector__robot_sessions

    def test_add_robot_creates_and_connects_session(
        self, fleet_connector, mock_robot_session_pool
    ):
        fleet_connector.add_robot(RobotConfig(robot_id="R3"))

        assert "R3" in fleet_connector.robot_ids
        assert any(rc.robot_id == "R3" for rc in fleet_connector.config.fleet)
        assert "R3" in self._sessions(fleet_connector)
        mock_robot_session_pool.get_session.assert_any_call("R3", robot_name="R3")

    def test_add_robot_duplicate_raises(self, fleet_connector, mock_robot_session_pool):
        mock_robot_session_pool.get_session.reset_mock()
        with pytest.raises(ValueError):
            fleet_connector.add_robot(RobotConfig(robot_id="TestRobot1"))

        # Fleet unchanged and no new session created.
        assert fleet_connector.robot_ids == ["TestRobot1", "TestRobot2"]
        mock_robot_session_pool.get_session.assert_not_called()

    def test_remove_robot_frees_session_and_clears_state(
        self, fleet_connector, mock_robot_session_pool
    ):
        # Seed per-robot state that must be cleaned up.
        fleet_connector._FleetConnector__last_published_frame_ids["TestRobot1"] = "map"
        fleet_connector._FleetConnector__pending_system_stats["TestRobot1"] = {"x": 1}

        fleet_connector.remove_robot("TestRobot1")

        mock_robot_session_pool.free_robot_session.assert_called_once_with("TestRobot1")
        assert "TestRobot1" not in fleet_connector.robot_ids
        assert all(rc.robot_id != "TestRobot1" for rc in fleet_connector.config.fleet)
        assert "TestRobot1" not in self._sessions(fleet_connector)
        assert (
            "TestRobot1"
            not in fleet_connector._FleetConnector__last_published_frame_ids
        )
        assert "TestRobot1" not in fleet_connector._FleetConnector__pending_system_stats

    def test_remove_robot_unknown_is_noop(
        self, fleet_connector, mock_robot_session_pool, caplog
    ):
        fleet_connector.remove_robot("does-not-exist")

        mock_robot_session_pool.free_robot_session.assert_not_called()
        assert fleet_connector.robot_ids == ["TestRobot1", "TestRobot2"]
        assert "not in the fleet" in caplog.text

    def test_publish_to_removed_robot_does_not_resurrect_session(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Accessing a removed robot returns None and publishing to it is a graceful
        skip that must NOT silently recreate a zombie session."""
        fleet_connector.remove_robot("TestRobot1")

        # The accessor returns None for a robot with no active session.
        assert fleet_connector._get_robot_session("TestRobot1") is None

        # Publishing tolerates the missing robot: no raise, and no resurrection via the
        # pool.
        mock_robot_session_pool.get_session.reset_mock()
        fleet_connector.publish_robot_odometry("TestRobot1", linear_speed=1.0)
        fleet_connector.publish_robot_pose("TestRobot1", 1.0, 2.0, 3.0, "map1")
        fleet_connector.publish_robot_key_values("TestRobot1", foo="bar")
        assert "TestRobot1" not in self._sessions(fleet_connector)
        mock_robot_session_pool.get_session.assert_not_called()

    def test_update_fleet_reconciles_diff(
        self, fleet_connector, mock_robot_session_pool
    ):
        mock_robot_session_pool.get_session.reset_mock()
        mock_robot_session_pool.free_robot_session.reset_mock()

        fleet_connector.update_fleet(
            [RobotConfig(robot_id="TestRobot2"), RobotConfig(robot_id="R3")]
        )

        # TestRobot1 dropped, R3 added, ordering preserved.
        assert fleet_connector.robot_ids == ["TestRobot2", "R3"]
        mock_robot_session_pool.free_robot_session.assert_called_once_with("TestRobot1")
        mock_robot_session_pool.get_session.assert_any_call("R3", robot_name="R3")
        # TestRobot2 untouched: not re-created, not freed.
        assert "TestRobot2" in self._sessions(fleet_connector)
        assert ("TestRobot2",) not in [
            c.args for c in mock_robot_session_pool.free_robot_session.call_args_list
        ]

    def test_update_fleet_duplicate_ids_raises(self, fleet_connector):
        with pytest.raises(ValueError):
            fleet_connector.update_fleet(
                [RobotConfig(robot_id="R3"), RobotConfig(robot_id="R3")]
            )

    def test_update_fleet_rolls_back_on_session_failure(
        self, fleet_connector, mock_robot_session_pool
    ):
        """If a session fails to connect mid-reconcile, the whole change rolls back:
        membership is untouched and every attempted add is freed from the pool."""
        before_ids = fleet_connector.robot_ids
        before_fleet = list(fleet_connector.config.fleet)

        # Fail when creating the 2nd newly-added robot's session.
        def failing_get_session(robot_id, robot_name=None):
            if robot_id == "R4":
                raise RuntimeError("connect failed")
            session = MagicMock(spec=RobotSession)
            session.robot_id = robot_id
            return session

        mock_robot_session_pool.get_session.side_effect = failing_get_session

        with pytest.raises(RuntimeError):
            fleet_connector.update_fleet(
                [
                    RobotConfig(robot_id="TestRobot1"),
                    RobotConfig(robot_id="TestRobot2"),
                    RobotConfig(robot_id="R3"),
                    RobotConfig(robot_id="R4"),
                ]
            )

        # Nothing committed: ids, config.fleet and the session map are as before.
        assert fleet_connector.robot_ids == before_ids
        assert fleet_connector.config.fleet == before_fleet
        assert set(self._sessions(fleet_connector)) == set(before_ids)
        # Both attempted adds were freed from the pool (incl. the half-built one).
        freed = {
            c.args[0] for c in mock_robot_session_pool.free_robot_session.call_args_list
        }
        assert {"R3", "R4"} <= freed

    def test_connect_materializes_initial_sessions(
        self, base_model, mock_robot_session_pool
    ):
        """__connect() creates a session per initial robot via update_fleet."""
        connector = FleetConnector(
            ConnectorRootConfig(
                **base_model,
                fleet=[
                    RobotConfig(robot_id="TestRobot1"),
                    RobotConfig(robot_id="TestRobot2"),
                ],
            )
        )
        connector.start()
        try:
            sleep(0.5)
            mock_robot_session_pool.get_session.assert_any_call(
                "TestRobot1", robot_name="TestRobot1"
            )
            mock_robot_session_pool.get_session.assert_any_call(
                "TestRobot2", robot_name="TestRobot2"
            )
            mock_robot_session_pool.free_robot_session.assert_not_called()
        finally:
            connector.stop()

    def test_disconnect_clears_sessions_for_restart(
        self, base_model, mock_robot_session_pool
    ):
        """stop() frees the pool sessions + clears the map so a later start()
        rebuilds and reconnects instead of reusing stale, disconnected sessions."""
        connector = FleetConnector(
            ConnectorRootConfig(
                **base_model,
                fleet=[RobotConfig(robot_id="TestRobot1")],
            )
        )
        connector.start()
        sleep(0.5)
        connector.stop()

        # The session was freed from the pool (which disconnects it) and the map
        # cleared. Freeing the pool — not just disconnecting — is what lets a restart
        # rebuild a fresh session (get_session skips connect() on a pool cache hit).
        mock_robot_session_pool.free_robot_session.assert_any_call("TestRobot1")
        assert connector._FleetConnector__robot_sessions == {}

        # Restart must recreate the session (to_add keys off __robot_sessions).
        mock_robot_session_pool.free_robot_session.reset_mock()
        connector.start()
        try:
            sleep(0.5)
            assert "TestRobot1" in connector._FleetConnector__robot_sessions
        finally:
            connector.stop()

    def test_runtime_empty_fleet_does_not_crash(
        self, fleet_connector, mock_robot_session_pool
    ):
        fleet_connector.remove_robot("TestRobot1")
        fleet_connector.remove_robot("TestRobot2")

        assert fleet_connector.robot_ids == []
        assert self._sessions(fleet_connector) == {}
        # Publishing pending stats over an empty fleet must be a safe no-op.
        fleet_connector._FleetConnector__publish_pending_system_stats()

    def test_cameras_registered_on_runtime_add(
        self, fleet_connector, mock_robot_session_pool
    ):
        robot = RobotConfig(
            robot_id="CamBot",
            cameras=[CameraConfig(video_url="rtsp://example/stream")],
        )
        fleet_connector.add_robot(robot)

        session = mock_robot_session_pool.get_session("CamBot")
        assert session.register_camera.call_count == 1
        args = session.register_camera.call_args
        assert args.args[0] == "0"
        assert isinstance(args.args[1], OpenCVCamera)

    def test_cameras_registered_once_at_startup(
        self, base_model, mock_robot_session_pool
    ):
        """Regression: moving camera reg into __initialize_session keeps it once."""
        connector = FleetConnector(
            ConnectorRootConfig(
                **base_model,
                fleet=[
                    RobotConfig(
                        robot_id="CamBot",
                        cameras=[CameraConfig(video_url="rtsp://example/stream")],
                    )
                ],
            )
        )
        connector.start()
        try:
            sleep(0.5)
            session = mock_robot_session_pool.get_session("CamBot")
            assert session.register_camera.call_count == 1
        finally:
            connector.stop()

    def test_update_fleet_keeps_config_of_unchanged_robot(
        self, fleet_connector, mock_robot_session_pool
    ):
        """A robot in both the old and new fleet keeps its existing RobotConfig and
        session even when the incoming RobotConfig differs (e.g. its cameras changed),
        so config.fleet stays consistent with the live session."""
        cam_a = CameraConfig(video_url="rtsp://example/a")
        fleet_connector.add_robot(RobotConfig(robot_id="CamBot", cameras=[cam_a]))
        session = mock_robot_session_pool.get_session("CamBot")
        session.register_camera.reset_mock()
        mock_robot_session_pool.get_session.reset_mock()
        mock_robot_session_pool.free_robot_session.reset_mock()

        # Re-declare the full fleet with CamBot's camera changed.
        fleet_connector.update_fleet(
            [
                RobotConfig(robot_id="TestRobot1"),
                RobotConfig(robot_id="TestRobot2"),
                RobotConfig(
                    robot_id="CamBot",
                    cameras=[CameraConfig(video_url="rtsp://example/b")],
                ),
            ]
        )

        # config.fleet still reports the original config; the session was untouched.
        cam_bot_config = next(
            rc for rc in fleet_connector.config.fleet if rc.robot_id == "CamBot"
        )
        assert cam_bot_config.cameras == [cam_a]
        mock_robot_session_pool.free_robot_session.assert_not_called()
        session.register_camera.assert_not_called()

    def test_publish_skips_removed_robot_without_disrupting_others(
        self, fleet_connector, mock_robot_session_pool
    ):
        """Publishing to a concurrently-removed robot is a graceful no-op skip; a robot
        still in the fleet keeps publishing in the same pass."""
        session2 = fleet_connector._get_robot_session("TestRobot2")
        fleet_connector.remove_robot("TestRobot1")

        # None of these raise for the removed robot.
        fleet_connector.publish_robot_pose("TestRobot1", 1.0, 2.0, 3.0, "map1")
        fleet_connector.publish_robot_odometry("TestRobot1", linear_speed=1.0)
        fleet_connector.publish_robot_key_values("TestRobot1", foo="bar")
        fleet_connector.publish_robot_map("TestRobot1", "map1")

        # A still-present robot publishes normally.
        fleet_connector.publish_robot_odometry("TestRobot2", linear_speed=2.0)
        session2.publish_odometry.assert_called_once_with(linear_speed=2.0)

    def test_add_remove_bypass_overridden_update_fleet(
        self, base_model, mock_robot_session_pool
    ):
        """add_robot/remove_robot reconcile via the private path, so a subclass that
        overrides the public update_fleet cannot intercept or break them."""
        override_calls = []

        class CustomFleetConnector(FleetConnector):
            def update_fleet(self, fleet):
                override_calls.append(list(fleet))  # no reconcile

        CustomFleetConnector.__abstractmethods__ = frozenset()
        connector = _seed_sessions(
            CustomFleetConnector(
                ConnectorRootConfig(**base_model, fleet=[RobotConfig(robot_id="R1")])
            )
        )

        connector.add_robot(RobotConfig(robot_id="R2"))
        assert "R2" in connector.robot_ids
        assert "R2" in self._sessions(connector)

        connector.remove_robot("R1")
        assert "R1" not in connector.robot_ids
        assert "R1" not in self._sessions(connector)

        # The overridden public update_fleet was never invoked by the wrappers.
        assert override_calls == []

    def test_connect_logs_initialized_session_count(
        self, base_model, mock_robot_session_pool
    ):
        """__connect logs how many sessions it created so an empty/misconfigured fleet
        is not silent."""
        # Capture directly off the connector logger: it inherits root's WARNING level
        # and may not propagate to caplog under the project's logging setup.
        logger = logging.getLogger("inorbit_connector.connector")
        messages = []
        handler = logging.Handler()
        handler.emit = lambda record: messages.append(record.getMessage())
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.INFO)
        try:
            connector = FleetConnector(
                ConnectorRootConfig(**base_model, fleet=[RobotConfig(robot_id="R1")])
            )
            connector.start()
            try:
                sleep(0.5)
            finally:
                connector.stop()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

        assert any("Initialized 1 robot session(s)" in m for m in messages)

    def test_thread_safety_smoke(self, fleet_connector):
        """Concurrent add/remove on a SHARED id set must keep the fleet's internal
        structures consistent. The shared ids force real contention on __fleet_lock —
        without it the read-modify-write in add/remove would corrupt config.fleet or
        desync it from the session map. Duplicate adds racing each other are expected
        and raise ValueError, which the workers swallow."""
        shared_ids = [f"T{i}" for i in range(8)]

        def worker():
            for _ in range(50):
                for rid in shared_ids:
                    try:
                        fleet_connector.add_robot(RobotConfig(robot_id=rid))
                    except ValueError:
                        # Another thread won the race to add this id — expected.
                        pass
                    fleet_connector.remove_robot(rid)  # no-op if already gone

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Deterministic cleanup so the final assertion doesn't hinge on interleaving.
        for rid in shared_ids:
            fleet_connector.remove_robot(rid)

        # The original fleet remains, with no duplicates, and robot_ids agrees with the
        # live session map (the invariant the lock protects).
        ids = fleet_connector.robot_ids
        assert sorted(ids) == ["TestRobot1", "TestRobot2"]
        assert len(ids) == len(set(ids))
        assert set(self._sessions(fleet_connector)) == {"TestRobot1", "TestRobot2"}


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
        """Test subclassing with all abstract methods implemented."""

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
            ConnectorRootConfig(
                api_key="valid_key",
                connection_config_url="https://valid.com/",
                connector_type="valid_connector",
                connector_config=DummyConfig(),
                fleet=[RobotConfig(robot_id="TestRobot")],
            ),
        )
        assert isinstance(connector, Connector)
        assert isinstance(connector, FleetConnector)  # Connector is a FleetConnector


class TestConnector:

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "connection_config_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_connector_not_abstract(self):
        with _concrete(Connector):
            yield

    @pytest.fixture
    def base_connector(self, base_model):
        return _seed_sessions(
            Connector(
                "TestRobot",
                ConnectorRootConfig(
                    **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
                ),
            )
        )

    def test_init(self, base_model):
        """Test Connector initialization."""
        robot_id = "TestRobot"
        config = ConnectorRootConfig(
            **base_model,
            fleet=[RobotConfig(robot_id=robot_id)],
        )

        connector = Connector(robot_id, config)
        assert connector.robot_id == robot_id
        assert connector.robot_ids == [robot_id]
        assert isinstance(connector.config, ConnectorRootConfig)
        assert len(connector.config.fleet) == 1
        assert connector.config.fleet[0].robot_id == robot_id
        assert connector._logger.name == Connector.__module__

    def test_init_with_robot_key(self, base_model, mock_robot_session_pool):
        """Test initialization with robot key."""
        config = ConnectorRootConfig(
            **base_model,
            inorbit_robot_key="valid_robot_key",
            fleet=[RobotConfig(robot_id="TestRobot")],
        )
        robot_id = "TestRobot"

        connector = _seed_sessions(Connector(robot_id, config))
        session = connector._get_session()
        assert session.robot_id == "TestRobot"

    def test_get_session(self, base_connector, mock_robot_session_pool):
        """Test that _get_session returns the session for the single robot."""
        session = base_connector._get_session()
        assert session is not None
        assert session.robot_id == "TestRobot"

    def test_get_session_raises_without_active_session(
        self, base_model, mock_robot_session_pool
    ):
        """_get_session keeps the strict contract: it raises (not returns None) when
        the robot has no active session, e.g. before the connector connects."""
        connector = Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
        with pytest.raises(KeyError):
            connector._get_session()

    def test_fleet_mutation_methods_raise(self, base_connector):
        """Single-robot Connector blocks the runtime fleet-mutation API."""
        with pytest.raises(NotImplementedError):
            base_connector.update_fleet([RobotConfig(robot_id="X")])
        with pytest.raises(NotImplementedError):
            base_connector.add_robot(RobotConfig(robot_id="X"))
        with pytest.raises(NotImplementedError):
            base_connector.remove_robot("TestRobot")

    def test_start_still_creates_session_despite_blocked_update_fleet(
        self, base_model, mock_robot_session_pool
    ):
        """__connect uses the private reconcile, so startup works though
        update_fleet is blocked."""
        connector = Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
        connector.start()
        try:
            sleep(0.5)
            mock_robot_session_pool.get_session.assert_any_call(
                "TestRobot", robot_name="TestRobot"
            )
        finally:
            connector.stop()

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
        connector = _seed_sessions(
            Connector(
                "TestRobot",
                ConnectorRootConfig(
                    **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
                ),
            )
        )

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
        connector = _seed_sessions(
            Connector(
                "TestRobot",
                ConnectorRootConfig(
                    **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
                ),
            )
        )

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
        connector = _seed_sessions(
            Connector(
                "TestRobot",
                ConnectorRootConfig(
                    **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
                ),
            )
        )

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

    def test_publish_key_values_injects_connector_type(
        self, base_connector, mock_robot_session_pool
    ):
        """publish_key_values injects connector_type automatically."""
        base_connector.publish_key_values(foo="bar")
        session = base_connector._get_session()
        session.publish_key_values.assert_called_with(
            {"connector_type": DummyConfig.CONNECTOR_TYPE, "foo": "bar"}
        )

    def test_publish_key_values_connector_type_overridable(
        self, base_connector, mock_robot_session_pool
    ):
        """Subclass can override connector_type via kwargs."""
        base_connector.publish_key_values(connector_type="custom")
        session = base_connector._get_session()
        session.publish_key_values.assert_called_with({"connector_type": "custom"})

    def test_publish_system_stats_stores_stats(
        self, base_connector, mock_robot_session_pool
    ):
        """Test publish_system_stats stores stats for deferred publishing."""
        base_connector.publish_system_stats(cpu_load_percentage=0.5)

        # Stats should be stored, not published immediately
        session = base_connector._get_session()
        session.publish_system_stats.assert_not_called()

        # Verify stats were stored
        pending_stats = base_connector._FleetConnector__pending_system_stats
        assert base_connector.robot_id in pending_stats
        assert pending_stats[base_connector.robot_id]["cpu_load_percentage"] == 0.5

    def test_is_robot_online_default_implementation(self, base_connector):
        """Test that _is_robot_online returns True by default."""
        assert base_connector._is_robot_online() is True

    def test_is_fleet_robot_online_delegates_to_is_robot_online(self, base_connector):
        """Test that _is_fleet_robot_online delegates to _is_robot_online."""
        assert base_connector._is_fleet_robot_online("TestRobot") is True

    @pytest.mark.asyncio
    async def test_inorbit_robot_command_handler_delegates(self, base_connector):
        """Test _inorbit_robot_command_handler delegates to _inorbit_command_handler."""
        base_connector._inorbit_command_handler = AsyncMock()

        await base_connector._inorbit_robot_command_handler(
            "TestRobot", "test_cmd", ["arg1"], {"opt": "val"}
        )

        base_connector._inorbit_command_handler.assert_awaited_once_with(
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
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
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
        """Test environment variables are set from config."""
        base_model["env_vars"] = {"ENV_VAR": "env_value"}
        Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
        assert "ENV_VAR" in os.environ
        assert os.environ["ENV_VAR"] == "env_value"

    @pytest.mark.asyncio
    async def test_start_stop_integration(self, base_model):
        """Integration test for start/stop functionality."""
        connector = Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
        connector._execution_loop = AsyncMock()
        connector._connect = AsyncMock()
        connector._disconnect = AsyncMock()

        connector.start()
        sleep(0.5)
        assert connector._FleetConnector__loop.is_running()

        connector.stop()
        assert not connector._FleetConnector__loop.is_running()

    @pytest.mark.asyncio
    async def test_fetch_map_default_returns_none(self, base_connector):
        """Test that default fetch_map returns None."""
        result = await base_connector.fetch_map("frame1")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_robot_map_delegates_to_fetch_map(self, base_connector):
        """Test that fetch_robot_map delegates to fetch_map."""
        from inorbit_connector.models import MapConfigTemp

        mock_map = MapConfigTemp(
            image=b"test_image",
            map_id="test_map",
            origin_x=0.0,
            origin_y=0.0,
            resolution=0.05,
        )
        base_connector.fetch_map = AsyncMock(return_value=mock_map)

        result = await base_connector.fetch_robot_map("TestRobot", "frame1")

        # Verify fetch_map was called with just frame_id
        base_connector.fetch_map.assert_awaited_once_with("frame1")
        assert result == mock_map


class TestConnectorCommandHandler:

    @pytest.fixture
    def base_model(self):
        return {
            "api_key": "valid_key",
            "connection_config_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_connector_not_abstract(self):
        with _concrete(Connector):
            yield

    @pytest.fixture
    def base_connector(self, base_model):
        return _seed_sessions(
            Connector(
                "TestRobot",
                ConnectorRootConfig(
                    **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
                ),
            )
        )

    @pytest.mark.asyncio
    async def test_register_command_handler_by_default(
        self, base_model, mock_robot_session_pool
    ):
        """Test that command handler is registered by default."""
        connector = Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
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
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
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
        connector = Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
        connector._connect = AsyncMock()

        # Initialize sessions
        await connector._FleetConnector__connect()

        # Verify callback was set
        session = connector._get_session()
        session.set_online_status_callback.assert_called_once()

        # Verify the callback calls _is_robot_online
        callback = session.set_online_status_callback.call_args[0][0]
        assert callback() is True  # Should return True by default

    def test_handle_command_exception_with_command_failure(
        self, base_model, mock_robot_session_pool
    ):
        """Test CommandFailure exceptions are handled and passed to result_function."""
        connector = Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
        result_function = MagicMock()

        command_failure = CommandFailure(
            execution_status_details="Command execution failed",
            stderr="Error details here",
        )

        connector._handle_command_exception(
            command_failure,
            "test_command",
            "TestRobot",
            ["arg1"],
            {"result_function": result_function},
        )

        result_function.assert_called_once_with(
            CommandResultCode.FAILURE,
            execution_status_details="Command execution failed",
            stderr="Error details here",
        )

    def test_handle_command_exception_with_generic_exception(
        self, base_model, mock_robot_session_pool
    ):
        """Test generic exceptions are handled and passed to result_function."""
        connector = Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
        result_function = MagicMock()

        error = ValueError("Something went wrong")

        connector._handle_command_exception(
            error,
            "test_command",
            "TestRobot",
            ["arg1"],
            {"result_function": result_function},
        )

        result_function.assert_called_once_with(
            CommandResultCode.FAILURE,
            execution_status_details="An error occurred executing custom command",
            stderr="Something went wrong",
        )

    def test_handle_command_exception_without_message(
        self, base_model, mock_robot_session_pool
    ):
        """Test that exceptions without a message use the class name as stderr."""
        connector = Connector(
            "TestRobot",
            ConnectorRootConfig(
                **base_model, fleet=[RobotConfig(robot_id="TestRobot")]
            ),
        )
        result_function = MagicMock()

        class CustomException(Exception):
            pass

        error = CustomException()

        connector._handle_command_exception(
            error,
            "test_command",
            "TestRobot",
            ["arg1"],
            {"result_function": result_function},
        )

        result_function.assert_called_once_with(
            CommandResultCode.FAILURE,
            execution_status_details="An error occurred executing custom command",
            stderr="CustomException",
        )
