# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

from datetime import datetime, timezone
from typing import Dict, List

from pydantic import BaseModel, Field

from inorbit_connector.waypoint_sync.models import (
    ANNOTATION_SYNC_ORIGIN_PROPERTY,
    ConfigObjectMetadata,
    SpatialAnnotation,
    WaypointAnnotationSpec,
    WaypointData,
)


class MockPose(BaseModel):
    """Custom pose format used by the mock external system."""

    x: float
    y: float
    heading: float


class MockExternalPosition(BaseModel):
    """Custom position format returned by the mock external system."""

    external_id: str
    label: str
    pose: MockPose
    map_ref: str
    properties: Dict[str, str] = Field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_mock_positions() -> List[MockExternalPosition]:
    """Seed positions for the mock external system."""
    return [
        MockExternalPosition(
            external_id="mock-pos-1",
            label="Loading Dock",
            pose=MockPose(x=1.2, y=3.4, heading=0.1),
            map_ref="frameIdA",
            properties={"last_sync": "2025-01-12T00:00:00+00:00", "source": "mock"},
        ),
        MockExternalPosition(
            external_id="mock-pos-2",
            label="Storage A",
            pose=MockPose(x=5.6, y=7.8, heading=-0.5),
            map_ref="frameIdA",
            properties={"last_sync": "2025-01-12T00:00:00+00:00", "source": "mock"},
        ),
        MockExternalPosition(
            external_id="mock-pos-3",
            label="Floor 2 Lobby",
            pose=MockPose(x=2.4, y=6.1, heading=1.2),
            map_ref="frameIdB",
            properties={"last_sync": "2025-01-12T00:00:00+00:00", "source": "mock"},
        ),
        MockExternalPosition(
            external_id="mock-pos-4",
            label="Charging Bay",
            pose=MockPose(x=-3.2, y=1.8, heading=2.8),
            map_ref="frameIdB",
            properties={"last_sync": "2025-01-12T00:00:00+00:00", "source": "mock"},
        ),
    ]


class MockPositionProvider:
    """In-memory provider for mock external positions."""

    def __init__(self, seed_positions: List[MockExternalPosition]) -> None:
        self._positions: Dict[str, MockExternalPosition] = {
            position.external_id: position for position in seed_positions
        }

    async def list_positions(self, frame_id: str) -> List[MockExternalPosition]:
        """Return positions filtered by frame_id (matched against map_ref)."""
        return [pos for pos in self._positions.values() if pos.map_ref == frame_id]

    async def create_position(
        self, position: MockExternalPosition
    ) -> MockExternalPosition:
        created = self._touch(position)
        self._positions[created.external_id] = created
        return created

    async def update_position(
        self, position_id: str, position: MockExternalPosition
    ) -> MockExternalPosition:
        updated = self._touch(position, position_id=position_id)
        self._positions[position_id] = updated
        return updated

    async def delete_position(self, position_id: str) -> None:
        self._positions.pop(position_id, None)

    def _touch(
        self, position: MockExternalPosition, position_id: str | None = None
    ) -> MockExternalPosition:
        properties = dict(position.properties)
        properties["last_sync"] = _now_iso()
        updates = {"properties": properties}
        if position_id is not None and position.external_id != position_id:
            updates["external_id"] = position_id
        return position.model_copy(update=updates)


class MockAnnotationConverter:
    """Convert between mock positions and InOrbit waypoint annotations."""

    def __init__(
        self,
        signature_value: str,
        company_id: str,
        location_id: str,
        map_ref: str,
    ) -> None:
        self._signature_value = signature_value
        self._scope = f"tag/{company_id}/{location_id}"
        self._map_ref = map_ref

    def position_to_annotation(
        self, position: MockExternalPosition, frame_id: str
    ) -> SpatialAnnotation:
        """Convert a position to an InOrbit waypoint annotation.

        Args:
            position: The external position to convert
            frame_id: The frame/map ID for this annotation
        """
        properties = dict(position.properties)
        properties[ANNOTATION_SYNC_ORIGIN_PROPERTY] = self._signature_value
        return SpatialAnnotation(
            metadata=ConfigObjectMetadata(id=position.external_id, scope=self._scope),
            spec=WaypointAnnotationSpec(
                frameId=frame_id,
                label=position.label,
                data=WaypointData(
                    x=position.pose.x,
                    y=position.pose.y,
                    theta=position.pose.heading,
                ),
                properties=properties,
            ),
        )

    def annotation_to_position(
        self, annotation: SpatialAnnotation
    ) -> MockExternalPosition:
        properties = dict(annotation.spec.properties)
        return MockExternalPosition(
            external_id=annotation.metadata.id,
            label=annotation.spec.label,
            pose=MockPose(
                x=annotation.spec.data.x,
                y=annotation.spec.data.y,
                heading=annotation.spec.data.theta,
            ),
            map_ref=self._map_ref,
            properties=properties,
        )

    def get_position_id(self, position: MockExternalPosition) -> str:
        return position.external_id

    def has_sync_signature(
        self,
        annotation: SpatialAnnotation,
        signature_property: str,
        signature_value: str,
    ) -> bool:
        return annotation.spec.properties.get(signature_property) == signature_value
