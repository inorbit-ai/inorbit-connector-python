#!/usr/bin/env python

# Copyright 2024 InOrbit, Inc.
# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

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
    CommandFailure,
    CommandResultCode,
    Connector,
    FleetConnector,
)
from inorbit_connector.models import (
    ConnectorConfig,
    InorbitConnectorConfig,
    RobotConfig,
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
            ConnectorConfig(
                api_key="valid_key",
                api_url="https://valid.com/",
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
            ConnectorConfig(
                **base_model,
                fleet=[
                    RobotConfig(robot_id="TestRobot1"),
                    RobotConfig(robot_id="TestRobot2"),
                ],
            )
        )

    def test_init(self, base_model):
        config = ConnectorConfig(
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
        config = ConnectorConfig(
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
        connector = FleetConnector(
            ConnectorConfig(
                **base_model,
                fleet=[RobotConfig(robot_id="TestRobot1")],
            )
        )

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
            ConnectorConfig(
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
            ConnectorConfig(
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
            "api_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_fleet_connector_not_abstract(self):
        FleetConnector.__abstractmethods__ = set()

    @pytest.fixture
    def fleet_connector(self, base_model):
        return FleetConnector(
            ConnectorConfig(
                **base_model,
                fleet=[RobotConfig(robot_id="TestRobot1")],
            )
        )

    def test_fetch_robot_map_default_returns_none(self, fleet_connector):
        """Test that default fetch_robot_map returns None."""
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            fleet_connector.fetch_robot_map("TestRobot1", "frame1")
        )
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
            "api_url": AnyHttpUrl("https://valid.com/"),
            "connector_type": "valid_connector",
            "connector_config": DummyConfig(),
        }

    @pytest.fixture(autouse=True)
    def make_fleet_connector_not_abstract(self):
        FleetConnector.__abstractmethods__ = set()

    @pytest.fixture
    def fleet_connector(self, base_model):
        return FleetConnector(
            ConnectorConfig(
                **base_model,
                fleet=[
                    RobotConfig(robot_id="TestRobot1"),
                    RobotConfig(robot_id="TestRobot2"),
                ],
            )
        )

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
                    ConnectorConfig(
                        **base_model,
                        fleet=[RobotConfig(robot_id="TestRobot1")],
                    ),
                    publish_connector_system_stats=True,
                )

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
                ConnectorConfig(
                    **base_model,
                    fleet=[RobotConfig(robot_id="TestRobot1")],
                ),
                publish_connector_system_stats=True,
            )

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
                    ConnectorConfig(
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_can_be_subclassed_with_all_abstract_methods_implemented(self):
        """Test subclassing with deprecated InorbitConnectorConfig."""

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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_init(self, base_model):
        """Test initialization with deprecated InorbitConnectorConfig."""
        config = InorbitConnectorConfig(**base_model)
        robot_id = "TestRobot"

        connector = Connector(robot_id, config)
        assert connector.robot_id == robot_id
        assert connector.robot_ids == [robot_id]  # Single robot wrapped in list
        # Config is converted from InorbitConnectorConfig to ConnectorConfig
        assert isinstance(connector.config, ConnectorConfig)
        assert len(connector.config.fleet) == 1
        assert connector.config.fleet[0].robot_id == robot_id
        assert connector._logger.name == Connector.__module__

    def test_init_with_connector_config(self, base_model):
        """Test initialization with new ConnectorConfig API."""
        robot_id = "TestRobot"
        config = ConnectorConfig(
            **base_model,
            fleet=[RobotConfig(robot_id=robot_id)],
        )

        connector = Connector(robot_id, config)
        assert connector.robot_id == robot_id
        assert connector.robot_ids == [robot_id]
        assert isinstance(connector.config, ConnectorConfig)
        assert len(connector.config.fleet) == 1
        assert connector.config.fleet[0].robot_id == robot_id

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_init_with_robot_key(self, base_model, mock_robot_session_pool):
        """Test initialization with robot key using deprecated InorbitConnectorConfig."""
        config = InorbitConnectorConfig(
            **base_model, inorbit_robot_key="valid_robot_key"
        )
        robot_id = "TestRobot"

        connector = Connector(robot_id, config)
        # Session is created on-demand, check when accessed
        session = connector._get_session()
        assert session.robot_id == "TestRobot"

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_get_session(self, base_connector, mock_robot_session_pool):
        """Test that _get_session returns the session for the single robot."""
        session = base_connector._get_session()
        assert session is not None
        assert session.robot_id == "TestRobot"
        mock_robot_session_pool.get_session.assert_called()

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_publish_map(self, base_model, mock_robot_session_pool):
        """Test publish_map delegates to FleetConnector.publish_robot_map (deprecated config)."""
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_publish_pose(self, base_model, mock_robot_session_pool):
        """Test publish_pose delegates to FleetConnector.publish_robot_pose (deprecated config)."""
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_publish_pose_updates_maps(self, base_model, mock_robot_session_pool):
        """Test that publishing pose with new frame_id updates the map (deprecated config)."""
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_publish_odometry(self, base_connector, mock_robot_session_pool):
        """Test publish_odometry delegates correctly."""
        base_connector.publish_odometry(linear_speed=1.0, angular_speed=0.5)

        session = base_connector._get_session()
        session.publish_odometry.assert_called()

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_publish_key_values(self, base_connector, mock_robot_session_pool):
        """Test publish_key_values delegates correctly."""
        base_connector.publish_key_values(key1="value1")

        session = base_connector._get_session()
        session.publish_key_values.assert_called()

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_is_robot_online_default_implementation(self, base_connector):
        """Test that _is_robot_online returns True by default."""
        assert base_connector._is_robot_online() is True

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_is_fleet_robot_online_delegates_to_is_robot_online(self, base_connector):
        """Test that _is_fleet_robot_online delegates to _is_robot_online."""
        assert base_connector._is_fleet_robot_online("TestRobot") is True

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    async def test_inorbit_robot_command_handler_delegates(self, base_connector):
        """Test that _inorbit_robot_command_handler delegates to _inorbit_command_handler."""
        base_connector._inorbit_command_handler = AsyncMock()

        await base_connector._inorbit_robot_command_handler(
            "TestRobot", "test_cmd", ["arg1"], {"opt": "val"}
        )

        base_connector._inorbit_command_handler.assert_awaited_once_with(
            "test_cmd", ["arg1"], {"opt": "val"}
        )

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    async def test_register_user_scripts(
        self, base_model, tmp_path, mock_robot_session_pool
    ):
        """Test user scripts registration for single robot connector (deprecated config)."""
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_uses_env_vars(self, base_model):
        """Test environment variables with deprecated config."""
        base_model["env_vars"] = {"ENV_VAR": "env_value"}
        Connector("TestRobot", InorbitConnectorConfig(**base_model))
        assert "ENV_VAR" in os.environ
        assert os.environ["ENV_VAR"] == "env_value"

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    async def test_start_stop_integration(self, base_model):
        """Integration test for start/stop functionality (deprecated config)."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        connector._execution_loop = AsyncMock()
        connector._connect = AsyncMock()
        connector._disconnect = AsyncMock()

        connector.start()
        sleep(0.5)
        assert connector._FleetConnector__loop.is_running()

        connector.stop()
        assert not connector._FleetConnector__loop.is_running()

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    async def test_fetch_map_default_returns_none(self, base_connector):
        """Test that default fetch_map returns None."""
        result = await base_connector.fetch_map("frame1")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
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
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    async def test_register_command_handler_by_default(
        self, base_model, mock_robot_session_pool
    ):
        """Test that command handler is registered by default (deprecated config)."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
        connector._connect = AsyncMock()

        # Initialize sessions (this triggers command handler registration)
        await connector._FleetConnector__connect()

        # Verify register_command_callback was called
        session = connector._get_session()
        session.register_command_callback.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    async def test_does_not_register_when_disabled(
        self, base_model, mock_robot_session_pool
    ):
        """Test that command handler is not registered when disabled (deprecated config)."""
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
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    async def test_sets_online_status_callback(
        self, base_model, mock_robot_session_pool
    ):
        """Test that online status callback is set on EdgeSDK (deprecated config)."""
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_handle_command_exception_with_command_failure(
        self, base_model, mock_robot_session_pool
    ):
        """Test that CommandFailure exceptions are properly handled and passed to result_function."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_handle_command_exception_with_generic_exception(
        self, base_model, mock_robot_session_pool
    ):
        """Test that generic exceptions are handled and passed to result_function with generic message."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
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

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_handle_command_exception_without_message(
        self, base_model, mock_robot_session_pool
    ):
        """Test that exceptions without a message use the class name as stderr."""
        connector = Connector("TestRobot", InorbitConnectorConfig(**base_model))
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
