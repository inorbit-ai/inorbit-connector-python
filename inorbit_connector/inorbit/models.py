# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""InOrbit Config API models.

This module provides base models for InOrbit Config API objects and
SpatialAnnotation models for map annotations.

For more information, see:
https://developer.inorbit.ai/docs#configuration-management
"""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

TConfigSpec = TypeVar("TConfigSpec", bound=BaseModel)


class ConfigObjectMetadata(BaseModel):
    """Metadata for Config API objects.

    All Config API objects have metadata containing identity information.

    Attributes:
        id: Unique identifier for the object
        scope: Scope for the object (e.g., "tag/{companyId}/{locationId}")
    """

    id: str
    scope: str | None = None


class ConfigObject(BaseModel, Generic[TConfigSpec]):
    """Base model for InOrbit Config API objects.

    All Config API objects share this structure with apiVersion, kind,
    metadata, and spec. The spec field varies by kind.

    See https://developer.inorbit.ai/docs#configuration-management for
    detailed information about Config API objects.

    Attributes:
        apiVersion: Config API version (always "v0.1")
        kind: Object kind identifier
        metadata: Object metadata (id, scope)
        spec: Type-specific specification
    """

    apiVersion: Literal["v0.1"] = "v0.1"
    kind: str
    metadata: ConfigObjectMetadata
    spec: TConfigSpec


class WaypointData(BaseModel):
    """Pose data for waypoint annotations.

    Represents the position and orientation of a waypoint in the map frame.

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

    Attributes:
        type: Annotation type (always "waypoint")
        frameId: Map frame ID
        label: Human-readable label
        properties: Additional properties
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
    need to work with.

    Attributes:
        id: Annotation identifier
        spec: Waypoint annotation specification
    """

    id: str
    spec: WaypointAnnotationSpec


class SpatialAnnotation(ConfigObject[WaypointAnnotationSpec]):
    """InOrbit SpatialAnnotation model.

    Represents a spatial annotation in InOrbit's Config API format.
    Currently supports waypoint annotations (spec.type == "waypoint").

    Attributes:
        apiVersion: Config API version (always "v0.1")
        kind: Object kind (always "SpatialAnnotation")
        metadata: Annotation metadata (id, scope)
        spec: Waypoint annotation specification
    """

    kind: Literal["SpatialAnnotation"] = "SpatialAnnotation"
    spec: WaypointAnnotationSpec
