# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Tests for annotation synchronization framework."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Awaitable, Callable, cast
from pydantic import BaseModel, HttpUrl

from inorbit_connector.connector import FleetConnector
from inorbit_connector.models import ConnectorConfig, RobotConfig
from inorbit_connector.annotation_sync.models import (
    ANNOTATION_SYNC_ORIGIN_PROPERTY,
    AnnotationSyncConfig,
    AnnotationSyncMode,
)
from inorbit_connector.inorbit import (
    ConfigObject,
    ConfigObjectMetadata,
    SpatialAnnotation,
    SpatialAnnotationData,
    WaypointAnnotationSpec,
    WaypointData,
    InOrbitConfigAPI,
)
from inorbit_connector.annotation_sync import AnnotationSyncManager


class TestAnnotationSyncConfig:
    """Tests for AnnotationSyncConfig model."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = AnnotationSyncConfig()
        assert config.enabled is False
        assert config.mode == AnnotationSyncMode.EXTERNAL_TO_INORBIT
        assert config.sync_interval_seconds == 300

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = AnnotationSyncConfig(
            enabled=True,
            mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
            sync_interval_seconds=60,
            location_id="test-location",
        )
        assert config.enabled is True
        assert config.mode == AnnotationSyncMode.EXTERNAL_TO_INORBIT
        assert config.sync_interval_seconds == 60
        assert config.location_id == "test-location"

    def test_sync_interval_must_be_positive(self):
        """Test that sync_interval_seconds must be positive."""
        with pytest.raises(ValueError):
            AnnotationSyncConfig(sync_interval_seconds=0)
        with pytest.raises(ValueError):
            AnnotationSyncConfig(sync_interval_seconds=-1)


class TestSpatialAnnotation:
    """Tests for SpatialAnnotation model."""

    def test_create_annotation(self):
        """Test creating a spatial annotation."""
        annotation = SpatialAnnotation(
            metadata=ConfigObjectMetadata(
                id="test-id",
                scope="tag/company/location",
            ),
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=1.0, y=2.0, theta=0.5),
                label="Test Waypoint",
                frameId="map",
                properties={ANNOTATION_SYNC_ORIGIN_PROPERTY: "test"},
            ),
        )
        assert annotation.apiVersion == "v0.1"
        assert annotation.kind == "SpatialAnnotation"
        assert annotation.metadata.id == "test-id"
        assert annotation.spec.label == "Test Waypoint"
        assert annotation.spec.data.x == 1.0
        assert annotation.spec.type == "waypoint"

    def test_model_dump(self):
        """Test converting annotation to dict via model_dump."""
        annotation = SpatialAnnotation(
            metadata=ConfigObjectMetadata(id="test-id"),
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=1.0, y=2.0, theta=0.5),
                label="Test",
                frameId="map",
            ),
        )
        data = annotation.model_dump()
        assert data["apiVersion"] == "v0.1"
        assert data["metadata"]["id"] == "test-id"
        assert data["spec"]["data"]["x"] == 1.0
        assert data["spec"]["type"] == "waypoint"

    def test_model_validate(self):
        """Test creating annotation from dict via model_validate."""
        data = {
            "apiVersion": "v0.1",
            "kind": "SpatialAnnotation",
            "metadata": {"id": "test-id", "scope": "tag/test/loc"},
            "spec": {
                "type": "waypoint",
                "data": {"x": 1.0, "y": 2.0, "theta": 0.5},
                "label": "Test",
                "frameId": "map",
                "properties": {},
            },
        }
        annotation = SpatialAnnotation.model_validate(data)
        assert annotation.metadata.id == "test-id"
        assert annotation.spec.data.x == 1.0


class TestInOrbitConfigAPI:
    """Tests for InOrbitConfigAPI."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return InOrbitConfigAPI(
            base_url="https://api.test.inorbit.ai",
            api_key="test-api-key",
        )

    @pytest.mark.asyncio
    async def test_list_objects(self, client):
        """Test listing annotations."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "apiVersion": "v0.1",
                    "kind": "SpatialAnnotation",
                    "metadata": {"id": "1", "scope": "tag/test/loc"},
                    "spec": {
                        "type": "waypoint",
                        "data": {"x": 1.0, "y": 2.0, "theta": 0.0},
                        "label": "Waypoint 1",
                        "frameId": "map",
                        "properties": {},
                    },
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            result = await client.list_objects(
                kind="SpatialAnnotation", scope="tag/test/location"
            )
            assert len(result) == 1
            # list_objects returns ConfigObject, validate as SpatialAnnotation
            # Use the raw dict from the response since ConfigObject.model_dump() has issues
            raw_data = mock_response.json.return_value["items"][0]
            annotation = SpatialAnnotation.model_validate(raw_data)
            assert isinstance(annotation, SpatialAnnotation)
            assert annotation.metadata.id == "1"
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_object(self, client):
        """Test applying an annotation."""
        annotation = SpatialAnnotation(
            metadata=ConfigObjectMetadata(id="new-obj"),
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=1.0, y=2.0, theta=0.0),
                label="New Waypoint",
                frameId="map",
            ),
        )

        mock_response = MagicMock()
        mock_response.json.return_value = annotation.model_dump()
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.apply_object(annotation)
            assert isinstance(result, SpatialAnnotation)
            assert result.metadata.id == "new-obj"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_synchronize_creates_new_annotations(self, client):
        """Test synchronization creates new annotations."""
        with patch.object(client, "list_objects", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            with (
                patch.object(
                    client, "apply_object", new_callable=AsyncMock
                ) as mock_apply,
                patch.object(
                    client, "delete_object", new_callable=AsyncMock
                ) as mock_delete,
            ):
                new_annotation = SpatialAnnotation(
                    metadata=ConfigObjectMetadata(id="obj-1"),
                    spec=WaypointAnnotationSpec(
                        data=WaypointData(x=1.0, y=2.0, theta=0.0),
                        label="Obj 1",
                        frameId="map",
                    ),
                )

                stats = await client.synchronize_objects(
                    scope="tag/test/loc",
                    objects=[new_annotation],
                )

                assert stats["created"] == 1
                assert stats["updated"] == 0
                assert stats["deleted"] == 0
                mock_apply.assert_called_once()
                mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_synchronize_objects_raises_on_mixed_kinds(self, client):
        """Test synchronization raises ValueError when objects have mixed kinds."""
        annotation1 = SpatialAnnotation(
            metadata=ConfigObjectMetadata(id="obj-1"),
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=1.0, y=2.0, theta=0.0),
                label="Obj 1",
                frameId="map",
            ),
        )

        # Create a ConfigObject with a different kind using a minimal spec
        class OtherSpec(BaseModel):
            pass

        other_kind_obj = ConfigObject[OtherSpec](
            kind="OtherKind",
            metadata=ConfigObjectMetadata(id="obj-2"),
            spec=OtherSpec(),
        )

        with pytest.raises(ValueError) as exc_info:
            await client.synchronize_objects(
                scope="tag/test/loc",
                objects=[annotation1, other_kind_obj],
            )

        assert "has kind OtherKind but expected SpatialAnnotation" in str(
            exc_info.value
        )
        assert "All objects must have the same kind" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test closing the client."""
        with patch.object(
            client._client, "aclose", new_callable=AsyncMock
        ) as mock_close:
            await client.close()
            mock_close.assert_called_once()


class DummyConnector(FleetConnector):
    """Minimal connector for annotation sync lifecycle tests."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self.connected = False
        self.disconnected = False

    async def _connect(self) -> None:
        self.connected = True

    async def _disconnect(self) -> None:
        self.disconnected = True

    async def _execution_loop(self) -> None:
        return None

    async def _inorbit_robot_command_handler(
        self, robot_id: str, command_name: str, args: list, options: dict
    ) -> None:
        return None

    async def run_connect(self) -> None:
        connect_fn = cast(
            Callable[[], Awaitable[None]], getattr(self, "_FleetConnector__connect")
        )
        await connect_fn()

    async def run_disconnect(self) -> None:
        disconnect_fn = cast(
            Callable[[], Awaitable[None]], getattr(self, "_FleetConnector__disconnect")
        )
        await disconnect_fn()


class DummyConnectorConfig(BaseModel):
    """Minimal connector_config for ConnectorConfig."""

    pass


class TestAnnotationSyncLifecycle:
    """Tests for framework-managed annotation sync lifecycle."""

    @pytest.fixture
    def base_config(self):
        connector_config = DummyConnectorConfig()
        return ConnectorConfig(
            api_key="test-key",
            api_url=cast(HttpUrl, "https://api.inorbit.ai"),
            rest_api_url=cast(HttpUrl, "https://rest.inorbit.ai"),
            connector_type="test",
            connector_config=connector_config,
            fleet=[RobotConfig(robot_id="robot-1")],
            annotation_sync=AnnotationSyncConfig(
                enabled=True,
                mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
                location_id="location",
            ),
            account_id="company",
        )

    @pytest.fixture
    def fleet_config(self):
        """Config with multiple robots for fleet testing."""
        connector_config = DummyConnectorConfig()
        return ConnectorConfig(
            api_key="test-key",
            api_url=cast(HttpUrl, "https://api.inorbit.ai"),
            rest_api_url=cast(HttpUrl, "https://rest.inorbit.ai"),
            connector_type="test",
            connector_config=connector_config,
            fleet=[
                RobotConfig(robot_id="robot-1"),
                RobotConfig(robot_id="robot-2"),
                RobotConfig(robot_id="robot-3"),
            ],
            annotation_sync=AnnotationSyncConfig(
                enabled=True,
                mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
                location_id="location",
            ),
            account_id="company",
        )

    @pytest.mark.asyncio
    async def test_register_and_start_stop(self, base_config):
        """Test that sync is initialized during connect, and managers are created per frame_id."""
        connector = DummyConnector(base_config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        manager_instance = MagicMock()
        manager_instance.stop = AsyncMock()
        client_instance = MagicMock()
        client_instance.close = AsyncMock()
        mock_session = MagicMock()

        with (
            patch(
                "inorbit_connector.connector.InOrbitConfigAPI",
                return_value=client_instance,
            ) as client_cls,
            patch(
                "inorbit_connector.connector.AnnotationSyncManager",
                return_value=manager_instance,
            ) as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
            patch.object(connector, "_get_robot_session", return_value=mock_session),
        ):
            await connector.run_connect()

            # Client is created during connect
            client_cls.assert_called_once_with(
                base_url="https://rest.inorbit.ai/", api_key="test-key"
            )
            # Manager is NOT created during connect (lazy per frame_id)
            manager_cls.assert_not_called()

            # Simulate publishing a pose - this triggers manager creation
            connector.publish_robot_pose("robot-1", 1.0, 2.0, 0.0, frame_id="map1")
            manager_cls.assert_called_once()
            manager_instance.start.assert_called_once()

            await connector.run_disconnect()
            manager_instance.stop.assert_called_once()
            client_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_enabled_without_registration(self, base_config):
        """Test sync is not initialized when provider/converter not registered."""
        connector = DummyConnector(base_config)

        with (
            patch("inorbit_connector.inorbit.InOrbitConfigAPI") as client_cls,
            patch("inorbit_connector.connector.AnnotationSyncManager") as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
        ):
            await connector.run_connect()
            client_cls.assert_not_called()
            manager_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_enabled_without_api_key(self, base_config):
        """Test sync is not initialized without api_key."""
        config = base_config.model_copy(update={"api_key": None})
        connector = DummyConnector(config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        with (
            patch("inorbit_connector.inorbit.InOrbitConfigAPI") as client_cls,
            patch("inorbit_connector.connector.AnnotationSyncManager") as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
        ):
            await connector.run_connect()
            client_cls.assert_not_called()
            manager_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_enabled_without_account_id(self, base_config):
        """Test sync is not initialized without account_id."""
        config = base_config.model_copy(update={"account_id": None})
        connector = DummyConnector(config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        with (
            patch("inorbit_connector.inorbit.InOrbitConfigAPI") as client_cls,
            patch("inorbit_connector.connector.AnnotationSyncManager") as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
        ):
            await connector.run_connect()
            client_cls.assert_not_called()
            manager_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_disabled_in_config(self, base_config):
        """Test sync is not initialized when enabled=False."""
        config = base_config.model_copy(
            update={
                "annotation_sync": AnnotationSyncConfig(
                    enabled=False,
                    mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
                    location_id="location",
                )
            }
        )
        connector = DummyConnector(config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        with (
            patch("inorbit_connector.inorbit.InOrbitConfigAPI") as client_cls,
            patch("inorbit_connector.connector.AnnotationSyncManager") as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
        ):
            await connector.run_connect()
            client_cls.assert_not_called()
            manager_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_annotation_sync_config(self, base_config):
        """Test sync is not initialized when annotation_sync config is None."""
        config = base_config.model_copy(update={"annotation_sync": None})
        connector = DummyConnector(config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        with (
            patch("inorbit_connector.inorbit.InOrbitConfigAPI") as client_cls,
            patch("inorbit_connector.connector.AnnotationSyncManager") as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
        ):
            await connector.run_connect()
            client_cls.assert_not_called()
            manager_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_pose_with_none_frame_id_no_manager(self, base_config):
        """Test that publishing pose with None frame_id doesn't create manager."""
        connector = DummyConnector(base_config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        client_instance = MagicMock()
        client_instance.close = AsyncMock()
        mock_session = MagicMock()

        with (
            patch(
                "inorbit_connector.connector.InOrbitConfigAPI",
                return_value=client_instance,
            ),
            patch("inorbit_connector.connector.AnnotationSyncManager") as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
            patch.object(connector, "_get_robot_session", return_value=mock_session),
        ):
            await connector.run_connect()

            # Publish pose with None frame_id
            connector.publish_robot_pose("robot-1", 1.0, 2.0, 0.0, frame_id=None)
            manager_cls.assert_not_called()


class TestPerFrameSyncManager:
    """Tests for per-frame_id sync manager creation in fleet mode."""

    @pytest.fixture
    def fleet_config(self):
        """Config with multiple robots for fleet testing."""
        connector_config = DummyConnectorConfig()
        return ConnectorConfig(
            api_key="test-key",
            api_url=cast(HttpUrl, "https://api.inorbit.ai"),
            rest_api_url=cast(HttpUrl, "https://rest.inorbit.ai"),
            connector_type="test",
            connector_config=connector_config,
            fleet=[
                RobotConfig(robot_id="robot-1"),
                RobotConfig(robot_id="robot-2"),
                RobotConfig(robot_id="robot-3"),
                RobotConfig(robot_id="robot-4"),
            ],
            annotation_sync=AnnotationSyncConfig(
                enabled=True,
                mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
                location_id="location",
            ),
            account_id="company",
        )

    @pytest.mark.asyncio
    async def test_one_manager_per_frame_id(self, fleet_config):
        """Test that one manager is created per unique frame_id, not per robot."""
        connector = DummyConnector(fleet_config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        managers_created = []

        def create_manager(*args, **kwargs):
            manager = MagicMock()
            manager.stop = AsyncMock()
            managers_created.append(
                {"args": args, "kwargs": kwargs, "manager": manager}
            )
            return manager

        client_instance = MagicMock()
        client_instance.close = AsyncMock()
        mock_session = MagicMock()

        with (
            patch(
                "inorbit_connector.connector.InOrbitConfigAPI",
                return_value=client_instance,
            ),
            patch(
                "inorbit_connector.connector.AnnotationSyncManager",
                side_effect=create_manager,
            ),
            patch.object(connector, "_FleetConnector__initialize_sessions"),
            patch.object(connector, "_get_robot_session", return_value=mock_session),
        ):
            await connector.run_connect()

            # No managers created yet
            assert len(managers_created) == 0

            # Robots 1 and 2 on map1
            connector.publish_robot_pose("robot-1", 1.0, 2.0, 0.0, frame_id="map1")
            assert len(managers_created) == 1
            assert managers_created[0]["kwargs"]["frame_id"] == "map1"

            connector.publish_robot_pose("robot-2", 3.0, 4.0, 0.0, frame_id="map1")
            # Still only one manager for map1
            assert len(managers_created) == 1

            # Robots 3 and 4 on map2
            connector.publish_robot_pose("robot-3", 5.0, 6.0, 0.0, frame_id="map2")
            assert len(managers_created) == 2
            assert managers_created[1]["kwargs"]["frame_id"] == "map2"

            connector.publish_robot_pose("robot-4", 7.0, 8.0, 0.0, frame_id="map2")
            # Still only two managers total
            assert len(managers_created) == 2

            await connector.run_disconnect()

    @pytest.mark.asyncio
    async def test_multiple_frame_ids_all_managers_stopped(self, fleet_config):
        """Test that all managers are stopped on disconnect."""
        connector = DummyConnector(fleet_config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        managers = []

        def create_manager(*args, **kwargs):
            manager = MagicMock()
            manager.stop = AsyncMock()
            managers.append(manager)
            return manager

        client_instance = MagicMock()
        client_instance.close = AsyncMock()
        mock_session = MagicMock()

        with (
            patch(
                "inorbit_connector.connector.InOrbitConfigAPI",
                return_value=client_instance,
            ),
            patch(
                "inorbit_connector.connector.AnnotationSyncManager",
                side_effect=create_manager,
            ),
            patch.object(connector, "_FleetConnector__initialize_sessions"),
            patch.object(connector, "_get_robot_session", return_value=mock_session),
        ):
            await connector.run_connect()

            # Create managers for 3 different frame_ids
            connector.publish_robot_pose("robot-1", 1.0, 2.0, 0.0, frame_id="map1")
            connector.publish_robot_pose("robot-2", 3.0, 4.0, 0.0, frame_id="map2")
            connector.publish_robot_pose("robot-3", 5.0, 6.0, 0.0, frame_id="map3")

            assert len(managers) == 3

            # All managers should have start() called
            for manager in managers:
                manager.start.assert_called_once()

            await connector.run_disconnect()

            # All managers should have stop() called
            for manager in managers:
                manager.stop.assert_called_once()

            # Client should be closed
            client_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_same_robot_changing_frames(self, fleet_config):
        """Test that new manager is created when robot moves to new frame."""
        connector = DummyConnector(fleet_config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        managers_by_frame = {}

        def create_manager(*args, **kwargs):
            frame_id = kwargs.get("frame_id")
            manager = MagicMock()
            manager.stop = AsyncMock()
            managers_by_frame[frame_id] = manager
            return manager

        client_instance = MagicMock()
        client_instance.close = AsyncMock()
        mock_session = MagicMock()

        with (
            patch(
                "inorbit_connector.connector.InOrbitConfigAPI",
                return_value=client_instance,
            ),
            patch(
                "inorbit_connector.connector.AnnotationSyncManager",
                side_effect=create_manager,
            ),
            patch.object(connector, "_FleetConnector__initialize_sessions"),
            patch.object(connector, "_get_robot_session", return_value=mock_session),
        ):
            await connector.run_connect()

            # Robot starts on map1
            connector.publish_robot_pose("robot-1", 1.0, 2.0, 0.0, frame_id="map1")
            assert "map1" in managers_by_frame
            assert len(managers_by_frame) == 1

            # Robot publishes more poses on map1 - no new manager
            connector.publish_robot_pose("robot-1", 1.5, 2.5, 0.1, frame_id="map1")
            assert len(managers_by_frame) == 1

            # Robot moves to map2 - new manager created
            connector.publish_robot_pose("robot-1", 10.0, 20.0, 0.0, frame_id="map2")
            assert "map2" in managers_by_frame
            assert len(managers_by_frame) == 2

            # Robot moves back to map1 - no new manager (already exists)
            connector.publish_robot_pose("robot-1", 2.0, 3.0, 0.0, frame_id="map1")
            assert len(managers_by_frame) == 2

            await connector.run_disconnect()

    @pytest.mark.asyncio
    async def test_manager_receives_correct_frame_id(self, fleet_config):
        """Test that manager is constructed with correct frame_id."""
        connector = DummyConnector(fleet_config)
        provider = MagicMock()
        converter = MagicMock()
        connector.register_annotation_sync(provider, converter)

        manager_kwargs_list = []

        def create_manager(*args, **kwargs):
            manager = MagicMock()
            manager.stop = AsyncMock()
            manager_kwargs_list.append(kwargs)
            return manager

        client_instance = MagicMock()
        client_instance.close = AsyncMock()
        mock_session = MagicMock()

        with (
            patch(
                "inorbit_connector.connector.InOrbitConfigAPI",
                return_value=client_instance,
            ),
            patch(
                "inorbit_connector.connector.AnnotationSyncManager",
                side_effect=create_manager,
            ),
            patch.object(connector, "_FleetConnector__initialize_sessions"),
            patch.object(connector, "_get_robot_session", return_value=mock_session),
        ):
            await connector.run_connect()

            connector.publish_robot_pose(
                "robot-1", 1.0, 2.0, 0.0, frame_id="building-a-floor-1"
            )

            assert len(manager_kwargs_list) == 1
            kwargs = manager_kwargs_list[0]
            assert kwargs["frame_id"] == "building-a-floor-1"
            assert kwargs["account_id"] == "company"
            assert kwargs["signature_value"] == "test"
            assert kwargs["position_provider"] is provider
            assert kwargs["annotation_converter"] is converter

            await connector.run_disconnect()

    @pytest.mark.asyncio
    async def test_manager_started_immediately_on_creation(self, fleet_config):
        """Test that manager.start() is called immediately after creation."""
        connector = DummyConnector(fleet_config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        start_order = []

        def create_manager(*args, **kwargs):
            frame_id = kwargs.get("frame_id")
            manager = MagicMock()
            manager.stop = AsyncMock()
            manager.start = MagicMock(side_effect=lambda: start_order.append(frame_id))
            return manager

        client_instance = MagicMock()
        client_instance.close = AsyncMock()
        mock_session = MagicMock()

        with (
            patch(
                "inorbit_connector.connector.InOrbitConfigAPI",
                return_value=client_instance,
            ),
            patch(
                "inorbit_connector.connector.AnnotationSyncManager",
                side_effect=create_manager,
            ),
            patch.object(connector, "_FleetConnector__initialize_sessions"),
            patch.object(connector, "_get_robot_session", return_value=mock_session),
        ):
            await connector.run_connect()

            connector.publish_robot_pose("robot-1", 1.0, 2.0, 0.0, frame_id="mapA")
            connector.publish_robot_pose("robot-2", 3.0, 4.0, 0.0, frame_id="mapB")
            connector.publish_robot_pose("robot-3", 5.0, 6.0, 0.0, frame_id="mapC")

            # Verify start() was called in order for each new frame_id
            assert start_order == ["mapA", "mapB", "mapC"]

            await connector.run_disconnect()

    @pytest.mark.asyncio
    async def test_no_manager_when_sync_disabled(self, fleet_config):
        """Test no managers created when sync not enabled even with pose publishing."""
        config = fleet_config.model_copy(
            update={
                "annotation_sync": AnnotationSyncConfig(
                    enabled=False,
                    mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
                    location_id="location",
                )
            }
        )
        connector = DummyConnector(config)
        connector.register_annotation_sync(MagicMock(), MagicMock())
        mock_session = MagicMock()

        with (
            patch("inorbit_connector.inorbit.InOrbitConfigAPI") as client_cls,
            patch("inorbit_connector.connector.AnnotationSyncManager") as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
            patch.object(connector, "_get_robot_session", return_value=mock_session),
        ):
            await connector.run_connect()

            # Publish poses - should NOT create any managers
            connector.publish_robot_pose("robot-1", 1.0, 2.0, 0.0, frame_id="map1")
            connector.publish_robot_pose("robot-2", 3.0, 4.0, 0.0, frame_id="map2")

            client_cls.assert_not_called()
            manager_cls.assert_not_called()

            await connector.run_disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_with_no_managers(self, fleet_config):
        """Test disconnect works cleanly when no managers were ever created."""
        connector = DummyConnector(fleet_config)
        connector.register_annotation_sync(MagicMock(), MagicMock())

        client_instance = MagicMock()
        client_instance.close = AsyncMock()

        with (
            patch(
                "inorbit_connector.connector.InOrbitConfigAPI",
                return_value=client_instance,
            ),
            patch("inorbit_connector.connector.AnnotationSyncManager") as manager_cls,
            patch.object(connector, "_FleetConnector__initialize_sessions"),
        ):
            await connector.run_connect()

            # Don't publish any poses - no managers created
            manager_cls.assert_not_called()

            # Disconnect should work without errors
            await connector.run_disconnect()
            client_instance.close.assert_called_once()


# Mock position model for testing
class MockPosition(BaseModel):
    """Mock external position model."""

    id: str
    name: str
    x: float
    y: float
    theta: float = 0.0


SIGNATURE_VALUE = "test-connector"


class MockPositionProvider:
    """Mock implementation of ExternalAnnotationProvider."""

    def __init__(self):
        self.positions: list[MockPosition] = []
        self.created: list[MockPosition] = []
        self.updated: list[tuple[str, MockPosition]] = []
        self.deleted: list[str] = []

    async def list_positions(self, frame_id: str) -> list[MockPosition]:
        """Return all positions (no filtering in mock)."""
        return self.positions

    async def create_position(self, position: MockPosition) -> None:
        self.created.append(position)

    async def update_position(self, position_id: str, position: MockPosition) -> None:
        self.updated.append((position_id, position))

    async def delete_position(self, position_id: str) -> None:
        self.deleted.append(position_id)


class MockAnnotationConverter:
    """Mock implementation of AnnotationConverter."""

    def position_to_annotation(
        self, position: MockPosition, frame_id: str
    ) -> SpatialAnnotationData:
        """Convert position to annotation using provided frame_id."""
        return SpatialAnnotationData(
            id=position.id,
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=position.x, y=position.y, theta=position.theta),
                label=position.name,
                frameId=frame_id,
                properties={},
            ),
        )

    def annotation_to_position(
        self, annotation_data: SpatialAnnotationData
    ) -> MockPosition:
        return MockPosition(
            id=annotation_data.id,
            name=annotation_data.spec.label,
            x=annotation_data.spec.data.x,
            y=annotation_data.spec.data.y,
            theta=annotation_data.spec.data.theta,
        )

    def get_position_id(self, position: MockPosition) -> str:
        return position.id


class ConcreteAnnotationSyncManager(AnnotationSyncManager[MockPosition]):
    """Concrete implementation for testing."""

    pass


class TestAnnotationSyncManager:
    """Tests for AnnotationSyncManager."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return AnnotationSyncConfig(
            enabled=True,
            mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
            location_id="test-location",
        )

    @pytest.fixture
    def inorbit_client(self):
        """Create mock InOrbit client."""
        client = MagicMock(spec=InOrbitConfigAPI)
        client.list_objects = AsyncMock(return_value=[])
        client.apply_object = AsyncMock()
        client.synchronize_objects = AsyncMock(
            return_value={
                "created": 0,
                "updated": 0,
                "up_to_date": 0,
                "deleted": 0,
            }
        )
        return client

    @pytest.fixture
    def position_provider(self):
        """Create mock position provider."""
        return MockPositionProvider()

    @pytest.fixture
    def converter(self):
        """Create mock converter."""
        return MockAnnotationConverter()

    @pytest.fixture
    def manager(self, config, inorbit_client, position_provider, converter):
        """Create test manager."""
        return ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="test-map",
            signature_value=SIGNATURE_VALUE,
        )

    def test_get_scope(self, manager):
        """Test scope generation."""
        scope = manager._get_scope()
        assert scope == "tag/test-company/test-location"

    def test_get_scope_missing_account_id(
        self, inorbit_client, position_provider, converter
    ):
        """Test scope generation fails without account ID."""
        config = AnnotationSyncConfig(
            enabled=True,
            mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
            location_id="test-location",
        )
        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id=None,
            frame_id="test-map",
            signature_value=SIGNATURE_VALUE,
        )
        with pytest.raises(ValueError):
            manager._get_scope()

    @pytest.mark.asyncio
    async def test_sync_external_to_inorbit(
        self, manager, position_provider, inorbit_client
    ):
        """Test external to InOrbit sync."""
        position_provider.positions = [
            MockPosition(id="pos-1", name="Position 1", x=1.0, y=2.0),
            MockPosition(id="pos-2", name="Position 2", x=3.0, y=4.0),
        ]

        await manager.sync_external_to_inorbit()

        # Should call synchronize_objects with converted annotations
        inorbit_client.synchronize_objects.assert_called_once()
        call_kwargs = inorbit_client.synchronize_objects.call_args.kwargs
        assert len(call_kwargs["objects"]) == 2
        assert all(isinstance(a, SpatialAnnotation) for a in call_kwargs["objects"])

    @pytest.mark.asyncio
    async def test_sync_inorbit_to_external(
        self, config, inorbit_client, position_provider, converter
    ):
        """Test InOrbit to external sync."""
        config.mode = AnnotationSyncMode.INORBIT_TO_EXTERNAL
        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="test-map",
            signature_value=SIGNATURE_VALUE,
        )

        # Setup InOrbit annotations
        inorbit_client.list_objects.return_value = [
            SpatialAnnotation(
                metadata=ConfigObjectMetadata(id="ann-1"),
                spec=WaypointAnnotationSpec(
                    data=WaypointData(x=1.0, y=2.0, theta=0.0),
                    label="Annotation 1",
                    frameId="test-map",
                    properties={ANNOTATION_SYNC_ORIGIN_PROPERTY: SIGNATURE_VALUE},
                ),
            )
        ]

        stats = await manager.sync_inorbit_to_external()

        assert stats["created"] == 1
        assert len(position_provider.created) == 1
        assert isinstance(position_provider.created[0], MockPosition)

    @pytest.mark.asyncio
    async def test_sync_inorbit_to_external_filters_by_frame_id(
        self, config, inorbit_client, position_provider, converter
    ):
        """Test that sync_inorbit_to_external only processes annotations for manager's frame_id."""
        config.mode = AnnotationSyncMode.INORBIT_TO_EXTERNAL
        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="frame-1",
            signature_value=SIGNATURE_VALUE,
        )

        # Setup InOrbit annotations with different frame_ids
        inorbit_client.list_objects.return_value = [
            # Annotation for frame-1 (should be processed)
            SpatialAnnotation(
                metadata=ConfigObjectMetadata(id="ann-1"),
                spec=WaypointAnnotationSpec(
                    data=WaypointData(x=1.0, y=2.0, theta=0.0),
                    label="Annotation 1",
                    frameId="frame-1",
                    properties={ANNOTATION_SYNC_ORIGIN_PROPERTY: SIGNATURE_VALUE},
                ),
            ),
            # Annotation for frame-2 (should be filtered out)
            SpatialAnnotation(
                metadata=ConfigObjectMetadata(id="ann-2"),
                spec=WaypointAnnotationSpec(
                    data=WaypointData(x=3.0, y=4.0, theta=0.0),
                    label="Annotation 2",
                    frameId="frame-2",
                    properties={ANNOTATION_SYNC_ORIGIN_PROPERTY: SIGNATURE_VALUE},
                ),
            ),
            # Annotation for frame-1 without signature (should be filtered out)
            SpatialAnnotation(
                metadata=ConfigObjectMetadata(id="ann-3"),
                spec=WaypointAnnotationSpec(
                    data=WaypointData(x=5.0, y=6.0, theta=0.0),
                    label="Annotation 3",
                    frameId="frame-1",
                    properties={},
                ),
            ),
        ]

        stats = await manager.sync_inorbit_to_external()

        # Should only create position for ann-1 (frame-1 with signature)
        assert stats["created"] == 1
        assert len(position_provider.created) == 1
        assert position_provider.created[0].id == "ann-1"

    @pytest.mark.asyncio
    async def test_sync_once_disabled(
        self, config, inorbit_client, position_provider, converter
    ):
        """Test sync_once when sync is disabled."""
        config.enabled = False
        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="test-map",
            signature_value=SIGNATURE_VALUE,
        )

        # sync_once doesn't check enabled, it just runs based on mode
        # The enabled check is in start()
        result = await manager.sync_once()
        # Should still run and return results based on mode
        assert isinstance(result, dict)

    def test_start_disabled(self, config, inorbit_client, position_provider, converter):
        """Test start when sync is disabled."""
        config.enabled = False
        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="test-map",
            signature_value=SIGNATURE_VALUE,
        )

        manager.start()
        assert manager._sync_task is None

    @pytest.mark.asyncio
    async def test_frame_id_passed_to_list_positions(
        self, config, inorbit_client, converter
    ):
        """Test that frame_id is passed to provider's list_positions."""
        provider = MagicMock()
        provider.list_positions = AsyncMock(return_value=[])

        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="warehouse-floor-2",
            signature_value=SIGNATURE_VALUE,
        )

        await manager.sync_external_to_inorbit()

        # Verify list_positions was called with the correct frame_id
        provider.list_positions.assert_called_once_with("warehouse-floor-2")

    @pytest.mark.asyncio
    async def test_frame_id_passed_to_position_to_annotation(
        self, config, inorbit_client, position_provider
    ):
        """Test that frame_id is passed to converter's position_to_annotation."""
        converter = MagicMock()
        converter.position_to_annotation = MagicMock(
            return_value=SpatialAnnotationData(
                id="test",
                spec=WaypointAnnotationSpec(
                    data=WaypointData(x=1.0, y=2.0, theta=0.0),
                    label="Test",
                    frameId="factory-map",
                ),
            )
        )

        position_provider.positions = [
            MockPosition(id="pos-1", name="Position 1", x=1.0, y=2.0),
        ]

        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="factory-map",
            signature_value=SIGNATURE_VALUE,
        )

        await manager.sync_external_to_inorbit()

        # Verify position_to_annotation was called with position and frame_id
        converter.position_to_annotation.assert_called_once()
        call_args = converter.position_to_annotation.call_args
        assert call_args[0][0] == position_provider.positions[0]  # position
        assert call_args[0][1] == "factory-map"  # frame_id

    @pytest.mark.asyncio
    async def test_different_managers_use_different_frame_ids(
        self, config, inorbit_client
    ):
        """Test that different manager instances use their own frame_ids."""
        provider1 = MagicMock()
        provider1.list_positions = AsyncMock(return_value=[])
        provider2 = MagicMock()
        provider2.list_positions = AsyncMock(return_value=[])

        converter = MockAnnotationConverter()

        manager1 = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=provider1,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="map-alpha",
            signature_value=SIGNATURE_VALUE,
        )

        manager2 = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=provider2,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="map-beta",
            signature_value=SIGNATURE_VALUE,
        )

        await manager1.sync_external_to_inorbit()
        await manager2.sync_external_to_inorbit()

        provider1.list_positions.assert_called_once_with("map-alpha")
        provider2.list_positions.assert_called_once_with("map-beta")

    def test_manager_logger_includes_frame_id(
        self, config, inorbit_client, position_provider, converter
    ):
        """Test that manager logger name includes frame_id for debugging."""
        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="debug-map-123",
            signature_value=SIGNATURE_VALUE,
        )

        # Logger name should include frame_id
        assert "debug-map-123" in manager._logger.name

    def test_is_waypoint_annotation_with_typed_spatial_annotation(self, manager):
        """Test _is_waypoint_annotation with typed SpatialAnnotation."""
        # Waypoint annotation
        waypoint_ann = SpatialAnnotation(
            metadata=ConfigObjectMetadata(id="wp-1"),
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=1.0, y=2.0, theta=0.0),
                label="Waypoint 1",
                frameId="map",
            ),
        )
        assert manager._is_waypoint_annotation(waypoint_ann) is True

    def test_is_waypoint_annotation_with_dict_spec(self, manager):
        """Test _is_waypoint_annotation with ConfigObject having dict spec."""
        # Waypoint annotation with dict spec (simulating list_objects response)
        waypoint_dict = ConfigObject.model_construct(
            apiVersion="v0.1",
            kind="SpatialAnnotation",
            metadata=ConfigObjectMetadata(id="wp-1"),
            spec={
                "type": "waypoint",
                "frameId": "map",
                "label": "Waypoint 1",
                "data": {"x": 1.0, "y": 2.0, "theta": 0.0},
                "properties": {},
            },
        )
        assert manager._is_waypoint_annotation(waypoint_dict) is True

        # Non-waypoint annotation with dict spec
        non_waypoint_dict = ConfigObject.model_construct(
            apiVersion="v0.1",
            kind="SpatialAnnotation",
            metadata=ConfigObjectMetadata(id="ann-1"),
            spec={
                "type": "obstacle",
                "frameId": "map",
                "label": "Obstacle 1",
                "properties": {},
            },
        )
        assert manager._is_waypoint_annotation(non_waypoint_dict) is False

        # Wrong kind
        wrong_kind = ConfigObject.model_construct(
            apiVersion="v0.1",
            kind="OtherKind",
            metadata=ConfigObjectMetadata(id="obj-1"),
            spec={"type": "waypoint"},
        )
        assert manager._is_waypoint_annotation(wrong_kind) is False

    def test_is_waypoint_with_sync_signature_typed_annotation(self, manager):
        """Test _is_waypoint_with_sync_signature with typed SpatialAnnotation."""
        # Waypoint with matching signature
        waypoint_with_sig = SpatialAnnotation(
            metadata=ConfigObjectMetadata(id="wp-1"),
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=1.0, y=2.0, theta=0.0),
                label="Waypoint 1",
                frameId="map",
                properties={ANNOTATION_SYNC_ORIGIN_PROPERTY: SIGNATURE_VALUE},
            ),
        )
        assert manager._is_waypoint_with_sync_signature(waypoint_with_sig) is True

        # Waypoint without signature
        waypoint_no_sig = SpatialAnnotation(
            metadata=ConfigObjectMetadata(id="wp-2"),
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=2.0, y=3.0, theta=0.0),
                label="Waypoint 2",
                frameId="map",
                properties={},
            ),
        )
        assert manager._is_waypoint_with_sync_signature(waypoint_no_sig) is False

        # Waypoint with wrong signature
        waypoint_wrong_sig = SpatialAnnotation(
            metadata=ConfigObjectMetadata(id="wp-3"),
            spec=WaypointAnnotationSpec(
                data=WaypointData(x=3.0, y=4.0, theta=0.0),
                label="Waypoint 3",
                frameId="map",
                properties={ANNOTATION_SYNC_ORIGIN_PROPERTY: "other-connector"},
            ),
        )
        assert manager._is_waypoint_with_sync_signature(waypoint_wrong_sig) is False

    def test_is_waypoint_with_sync_signature_dict_spec(self, manager):
        """Test _is_waypoint_with_sync_signature with ConfigObject having dict spec."""
        # Waypoint with dict spec and matching signature
        waypoint_with_sig = ConfigObject.model_construct(
            apiVersion="v0.1",
            kind="SpatialAnnotation",
            metadata=ConfigObjectMetadata(id="wp-1"),
            spec={
                "type": "waypoint",
                "frameId": "map",
                "label": "Waypoint 1",
                "data": {"x": 1.0, "y": 2.0, "theta": 0.0},
                "properties": {ANNOTATION_SYNC_ORIGIN_PROPERTY: SIGNATURE_VALUE},
            },
        )
        assert manager._is_waypoint_with_sync_signature(waypoint_with_sig) is True

        # Waypoint with dict spec but no signature
        waypoint_no_sig = ConfigObject.model_construct(
            apiVersion="v0.1",
            kind="SpatialAnnotation",
            metadata=ConfigObjectMetadata(id="wp-2"),
            spec={
                "type": "waypoint",
                "frameId": "map",
                "label": "Waypoint 2",
                "data": {"x": 2.0, "y": 3.0, "theta": 0.0},
                "properties": {},
            },
        )
        assert manager._is_waypoint_with_sync_signature(waypoint_no_sig) is False

        # Waypoint with dict spec but wrong signature
        waypoint_wrong_sig = ConfigObject.model_construct(
            apiVersion="v0.1",
            kind="SpatialAnnotation",
            metadata=ConfigObjectMetadata(id="wp-3"),
            spec={
                "type": "waypoint",
                "frameId": "map",
                "label": "Waypoint 3",
                "data": {"x": 3.0, "y": 4.0, "theta": 0.0},
                "properties": {ANNOTATION_SYNC_ORIGIN_PROPERTY: "other-connector"},
            },
        )
        assert manager._is_waypoint_with_sync_signature(waypoint_wrong_sig) is False

        # Non-waypoint annotation (should return False)
        non_waypoint = ConfigObject.model_construct(
            apiVersion="v0.1",
            kind="SpatialAnnotation",
            metadata=ConfigObjectMetadata(id="ann-1"),
            spec={
                "type": "obstacle",
                "frameId": "map",
                "label": "Obstacle 1",
                "properties": {ANNOTATION_SYNC_ORIGIN_PROPERTY: SIGNATURE_VALUE},
            },
        )
        assert manager._is_waypoint_with_sync_signature(non_waypoint) is False

    @pytest.mark.asyncio
    async def test_sync_external_to_inorbit_uses_waypoint_filter(
        self, manager, position_provider, inorbit_client
    ):
        """Test that sync_external_to_inorbit uses the waypoint filter function."""
        position_provider.positions = [
            MockPosition(id="pos-1", name="Position 1", x=1.0, y=2.0),
        ]

        await manager.sync_external_to_inorbit()

        # Verify synchronize_objects was called with the filter function
        inorbit_client.synchronize_objects.assert_called_once()
        call_kwargs = inorbit_client.synchronize_objects.call_args.kwargs
        assert call_kwargs["filter_fn"] == manager._is_waypoint_with_sync_signature

    @pytest.mark.asyncio
    async def test_sync_external_to_inorbit_filters_dict_spec_annotations(
        self, config, inorbit_client, position_provider, converter
    ):
        """Test that sync_external_to_inorbit correctly filters ConfigObject with dict spec.

        This test verifies the fix for the bug where _has_sync_signature would
        crash when synchronize_objects calls list_objects and receives ConfigObject
        instances with dict specs.
        """
        manager = ConcreteAnnotationSyncManager(
            config=config,
            inorbit_config_client=inorbit_client,
            position_provider=position_provider,
            annotation_converter=converter,
            account_id="test-company",
            frame_id="test-map",
            signature_value=SIGNATURE_VALUE,
        )

        position_provider.positions = [
            MockPosition(id="pos-1", name="Position 1", x=1.0, y=2.0),
        ]

        # Mock list_objects to return ConfigObject with dict spec (as it does in reality)
        inorbit_client.list_objects = AsyncMock(
            return_value=[
                # Existing waypoint annotation with matching signature (should be filtered in)
                ConfigObject.model_construct(
                    apiVersion="v0.1",
                    kind="SpatialAnnotation",
                    metadata=ConfigObjectMetadata(id="existing-wp-1"),
                    spec={
                        "type": "waypoint",
                        "frameId": "test-map",
                        "label": "Existing Waypoint",
                        "data": {"x": 10.0, "y": 20.0, "theta": 0.0},
                        "properties": {
                            ANNOTATION_SYNC_ORIGIN_PROPERTY: SIGNATURE_VALUE
                        },
                    },
                ),
                # Non-waypoint annotation (should be filtered out)
                ConfigObject.model_construct(
                    apiVersion="v0.1",
                    kind="SpatialAnnotation",
                    metadata=ConfigObjectMetadata(id="obstacle-1"),
                    spec={
                        "type": "obstacle",
                        "frameId": "test-map",
                        "label": "Obstacle",
                        "properties": {},
                    },
                ),
                # Waypoint without signature (should be filtered out)
                ConfigObject.model_construct(
                    apiVersion="v0.1",
                    kind="SpatialAnnotation",
                    metadata=ConfigObjectMetadata(id="wp-no-sig"),
                    spec={
                        "type": "waypoint",
                        "frameId": "test-map",
                        "label": "Waypoint No Sig",
                        "data": {"x": 5.0, "y": 6.0, "theta": 0.0},
                        "properties": {},
                    },
                ),
            ]
        )

        # This should not raise AttributeError
        await manager.sync_external_to_inorbit()

        # Verify synchronize_objects was called
        inorbit_client.synchronize_objects.assert_called_once()
        # The filter should have been applied to the existing objects from list_objects
        # Only the waypoint with matching signature should be considered for update/delete
