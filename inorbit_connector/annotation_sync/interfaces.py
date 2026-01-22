# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Interfaces for annotation synchronization.

This module defines the interfaces that connectors must implement
to enable annotation synchronization between external systems and InOrbit.

Terminology:
    - **Annotation**: An InOrbit SpatialAnnotation object (kind: SpatialAnnotation).
      Currently, we support waypoint annotations (spec.type == "waypoint").
    - **Position**: A relevant position in the external system. This is the
      external system's representation of a location that maps to a waypoint
      annotation in InOrbit.
    - **External system**: The software the connector interacts with, such as
      a fleet manager (MiR Fleet, Bluebotics) or native robot software.

The framework uses generics for external positions (TExternalPosition),
requiring each connector to define its own Pydantic BaseModel subclass
for positions. InOrbit annotations are always represented as
SpatialAnnotation Pydantic models.
"""

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from inorbit_connector.annotation_sync.models import SpatialAnnotationData

# Generic type for external system positions (must be a Pydantic BaseModel)
TExternalPosition = TypeVar("TExternalPosition", bound=BaseModel)


@runtime_checkable
class ExternalAnnotationProvider(Protocol[TExternalPosition]):
    """Protocol for external annotation providers.

    Connectors implement this to provide CRUD access to positions in
    their external system. These positions correspond to waypoint
    annotations in InOrbit.

    The provider handles communication with the external system's API
    and returns positions in the connector's native format (TPosition).

    Note:
        This is called "AnnotationProvider" because it provides the
        external data that will become annotations in InOrbit. The
        current implementation focuses on positions (for waypoint
        annotations), but the interface is designed to support other
        annotation types in the future (zones, routes, etc.).
    """

    async def list_positions(self, frame_id: str) -> list[TExternalPosition]:
        """Fetch positions from the external system for a specific frame.

        Implementations should filter positions to only return those
        that belong to the specified frame_id (map).

        Args:
            frame_id: The frame/map ID to filter positions by

        Returns:
            List of positions in the external system's format that
            belong to the specified frame. Each position should contain
            at minimum an identifier and coordinates.
        """
        ...

    async def create_position(self, position: TExternalPosition) -> None:
        """Create a new position in the external system.

        Args:
            position: Position data in the external system's format

        Raises:
            Exception: If creation fails (implementation-specific)
        """
        ...

    async def update_position(
        self, position_id: str, position: TExternalPosition
    ) -> None:
        """Update an existing position in the external system.

        Args:
            position_id: Unique identifier of the position to update
            position: Updated position data

        Raises:
            Exception: If update fails (implementation-specific)
        """
        ...

    async def delete_position(self, position_id: str) -> None:
        """Delete a position from the external system.

        Args:
            position_id: Unique identifier of the position to delete

        Raises:
            Exception: If deletion fails (implementation-specific)
        """
        ...


@runtime_checkable
class AnnotationConverter(Protocol[TExternalPosition]):
    """Protocol for converting between positions and annotations.

    Connectors implement this to convert between their external system's
    position format and SpatialAnnotationData (id + spec only).

    The converter handles:
        - Converting external positions to SpatialAnnotationData
        - Converting SpatialAnnotationData back to external positions
        - Extracting position IDs for matching/comparison

    Note:
        The converter works with SpatialAnnotationData which contains only
        id and spec. The manager handles constructing full SpatialAnnotation
        objects with metadata, apiVersion, kind, and sync signatures.
    """

    def position_to_annotation(
        self, position: TExternalPosition, frame_id: str
    ) -> SpatialAnnotationData:
        """Convert an external position to SpatialAnnotationData.

        The resulting data should have:
            - id: Position identifier
            - spec.type == "waypoint"
            - Position data (x, y, theta) in spec.data
            - spec.frameId set to the provided frame_id

        Note:
            The manager will inject sync signatures automatically.
            Do not add sync-related properties to spec.properties.

        Args:
            position: Position from the external system
            frame_id: The frame/map ID for this annotation

        Returns:
            SpatialAnnotationData with type="waypoint" representing the position
        """
        ...

    def annotation_to_position(
        self, annotation_data: SpatialAnnotationData
    ) -> TExternalPosition:
        """Convert SpatialAnnotationData to an external position.

        Args:
            annotation_data: SpatialAnnotationData with type="waypoint"

        Returns:
            Position in the external system's format
        """
        ...

    def get_position_id(self, position: TExternalPosition) -> str:
        """Extract the unique identifier from a position.

        This ID is used to match positions with annotations during sync.

        Args:
            position: Position from the external system

        Returns:
            Unique identifier string
        """
        ...
