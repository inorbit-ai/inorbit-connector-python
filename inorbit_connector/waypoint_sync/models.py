# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""InOrbit Config API and annotation synchronization models.

This module provides:
    - Base models for InOrbit Config API objects
    - SpatialAnnotation model for map annotations
    - Configuration models for annotation synchronization

Config API objects share a common structure:
    - apiVersion: Always "v0.1"
    - kind: Object type (e.g., "SpatialAnnotation")
    - metadata: Object identity (id, scope)
    - spec: Type-specific specification

Terminology:
    - Annotation: An InOrbit SpatialAnnotation object (kind: SpatialAnnotation)
    - Position: A relevant position in the external system
    - External system: Fleet manager or robot software the connector integrates with
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Sync Configuration Models
# =============================================================================

ANNOTATION_SYNC_ORIGIN_PROPERTY = "syncOrigin"


class AnnotationSyncMode(str, Enum):
    """Synchronization modes for annotation synchronization.

    Attributes:
        EXTERNAL_TO_INORBIT: Sync from external system to InOrbit
            (external system is source of truth)
        INORBIT_TO_EXTERNAL: Sync from InOrbit to external system
            (InOrbit is source of truth)
        DISABLED: Synchronization is disabled
    """

    EXTERNAL_TO_INORBIT = "external_to_inorbit"
    INORBIT_TO_EXTERNAL = "inorbit_to_external"
    DISABLED = "disabled"


class AnnotationSyncConfig(BaseModel):
    """Configuration for annotation synchronization.

    This is a framework-level configuration that works with any connector
    implementing the ExternalAnnotationProvider and AnnotationConverter
    interfaces.

    Connectors can extend this class to add implementation-specific fields
    (e.g., map_id for MiR Fleet).

    Note:
        frame_id is not configured here. The framework automatically starts
        sync for each frame_id as poses are published, supporting fleet
        connectors with robots on multiple maps.

    Attributes:
        enabled: Enable annotation synchronization
        mode: Synchronization mode (default: DISABLED)
        sync_interval_seconds: Interval between syncs in seconds
        location_id: Location/tag ID for annotation scope in InOrbit
    """

    enabled: bool = False
    mode: AnnotationSyncMode = AnnotationSyncMode.DISABLED
    sync_interval_seconds: int = Field(default=300, gt=0)

    # InOrbit Config API settings
    location_id: Optional[str] = None


# =============================================================================
# Config API Base Models
# =============================================================================


class ConfigObjectMetadata(BaseModel):
    """Metadata for Config API objects.

    All Config API objects have metadata containing identity information.

    Attributes:
        id: Unique identifier for the object
        scope: Scope for the object (e.g., "tag/{companyId}/{locationId}")
    """

    id: str
    scope: Optional[str] = None


class ConfigObject(BaseModel):
    """Base model for InOrbit Config API objects.

    All Config API objects share this structure with apiVersion, kind,
    and metadata. The spec field varies by kind.

    Attributes:
        apiVersion: Config API version (always "v0.1")
        kind: Object kind identifier
        metadata: Object metadata (id, scope)
    """

    apiVersion: Literal["v0.1"] = "v0.1"
    kind: str
    metadata: ConfigObjectMetadata


# =============================================================================
# SpatialAnnotation Models
# =============================================================================


class WaypointData(BaseModel):
    """Pose data for waypoint annotations.

    Represents the position and orientation of a waypoint in the map frame.
    This data structure is specific to spatial annotations of type "waypoint".

    Attributes:
        x: X coordinate in the map frame (meters)
        y: Y coordinate in the map frame (meters)
        theta: Orientation in radians
    """

    x: float
    y: float
    theta: float


class WaypointAnnotationSpec(BaseModel):
    """Specification for waypoint spatial annotations.

    This is the spec structure for SpatialAnnotation objects with type="waypoint".

    Common fields across all spatial annotation types:
        - type: The annotation type identifier
        - frameId: Map frame ID (e.g., "map")
        - label: Human-readable label
        - properties: Additional key-value properties

    Waypoint-specific fields:
        - data: Pose data (x, y, theta)

    Attributes:
        type: Annotation type (always "waypoint" for this spec)
        frameId: Map frame ID
        label: Human-readable label for the annotation
        properties: Additional properties including sync signature
        data: Waypoint pose data
    """

    type: Literal["waypoint"] = "waypoint"
    frameId: str
    label: str
    properties: dict = Field(default_factory=dict)
    data: WaypointData


class SpatialAnnotationData(BaseModel):
    """Minimal annotation data for converter interface.

    Contains only the essential fields (id and spec) that converters
    need to work with. The manager handles constructing the full
    SpatialAnnotation with metadata, apiVersion, and kind.

    Attributes:
        id: Annotation identifier
        spec: Waypoint annotation specification
    """

    id: str
    spec: WaypointAnnotationSpec


class SpatialAnnotation(ConfigObject):
    """InOrbit SpatialAnnotation model.

    Represents a spatial annotation in InOrbit's Config API format.
    Inherits common fields from ConfigObject and adds the SpatialAnnotation spec.

    Currently supports waypoint annotations (spec.type == "waypoint").
    Future annotation types (zones, routes) will have different spec structures
    while sharing the common fields (frameId, label, properties).

    Attributes:
        apiVersion: Config API version (always "v0.1")
        kind: Object kind (always "SpatialAnnotation")
        metadata: Annotation metadata (id, scope)
        spec: Waypoint annotation specification

    Example:
        annotation = SpatialAnnotation(
            metadata=ConfigObjectMetadata(
                id="waypoint-001",
                scope="tag/company-id/location-id"
            ),
            spec=WaypointAnnotationSpec(
                frameId="map",
                label="Dock Station",
                data=WaypointData(x=1.0, y=2.0, theta=0.0),
                properties={"syncOrigin": "mir-fleet-connector"}
            )
        )
    """

    kind: Literal["SpatialAnnotation"] = "SpatialAnnotation"
    spec: WaypointAnnotationSpec
