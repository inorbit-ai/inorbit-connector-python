# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

from typing import Dict, List

from pydantic import BaseModel, Field

from inorbit_connector.inorbit import (
    SpatialAnnotationData,
    WaypointAnnotationSpec,
    WaypointData,
)


class MockPose(BaseModel):
    """Custom pose format used by the mock external system."""

    x: float
    y: float
    heading: float


class ExternalPosition(BaseModel):
    """Custom position format returned by the mock external system."""

    external_id: str
    label: str
    pose: MockPose
    map_ref: str
    properties: Dict[str, str] = Field(default_factory=dict)


def build_mock_positions() -> List[ExternalPosition]:
    """Seed positions for the mock external system."""
    return [
        ExternalPosition(
            external_id="mock-pos-1",
            label="Loading Dock",
            pose=MockPose(x=1.2, y=3.4, heading=0.1),
            map_ref="frameIdA",
            properties={"createdBy": "user1"},
        ),
        ExternalPosition(
            external_id="mock-pos-2",
            label="Storage A",
            pose=MockPose(x=5.6, y=7.8, heading=-0.5),
            map_ref="frameIdA",
            properties={"createdBy": "user2"},
        ),
        ExternalPosition(
            external_id="mock-pos-3",
            label="Floor 2 Lobby",
            pose=MockPose(x=2.4, y=6.1, heading=1.2),
            map_ref="map",
            properties={"type": "staging-position"},
        ),
        ExternalPosition(
            external_id="mock-pos-4",
            label="Charging Bay",
            pose=MockPose(x=-3.2, y=1.8, heading=2.8),
            map_ref="map",
            properties={"type": "parking"},
        ),
    ]


class MockPositionProvider:
    """In-memory provider for mock external positions."""

    def __init__(self, seed_positions: List[ExternalPosition]) -> None:
        self._positions: Dict[str, ExternalPosition] = {
            position.external_id: position for position in seed_positions
        }

    async def list_positions(self, frame_id: str) -> List[ExternalPosition]:
        """Return positions filtered by frame_id (matched against map_ref)."""
        return [pos for pos in self._positions.values() if pos.map_ref == frame_id]

    async def create_position(self, position: ExternalPosition) -> None:
        self._positions[position.external_id] = position

    async def update_position(
        self, position_id: str, position: ExternalPosition
    ) -> None:
        self._positions[position_id] = position

    async def delete_position(self, position_id: str) -> None:
        self._positions.pop(position_id, None)


class MockAnnotationConverter:
    """Convert between mock positions and SpatialAnnotationData."""

    def position_to_annotation(
        self, position: ExternalPosition, frame_id: str
    ) -> SpatialAnnotationData:
        """Convert a position to SpatialAnnotationData.

        Args:
            position: The external position to convert
            frame_id: The frame/map ID for this annotation
        """
        return SpatialAnnotationData(
            id=position.external_id,
            spec=WaypointAnnotationSpec(
                frameId=frame_id,
                label=position.label,
                data=WaypointData(
                    x=position.pose.x,
                    y=position.pose.y,
                    theta=position.pose.heading,
                ),
                properties=dict(position.properties),
            ),
        )

    def annotation_to_position(
        self, annotation_data: SpatialAnnotationData
    ) -> ExternalPosition:
        properties = dict(annotation_data.spec.properties)
        return ExternalPosition(
            external_id=annotation_data.id,
            label=annotation_data.spec.label,
            pose=MockPose(
                x=annotation_data.spec.data.x,
                y=annotation_data.spec.data.y,
                heading=annotation_data.spec.data.theta,
            ),
            map_ref=annotation_data.spec.frameId,
            properties=properties,
        )

    def get_position_id(self, position: ExternalPosition) -> str:
        return position.external_id
