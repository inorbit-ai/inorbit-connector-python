# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Annotation synchronization framework for InOrbit connectors.

This package provides a reusable framework for synchronizing annotations
(currently waypoints) between external systems and InOrbit's Config API.

Terminology:
    - Annotation: InOrbit SpatialAnnotation object (kind: SpatialAnnotation)
    - Position: Waypoint/location in the external system
    - External system: Fleet manager or robot software

Modules:
    config_client: InOrbit Config API client for managing annotations
    models: Configuration and data models (WaypointSyncConfig, SpatialAnnotation)
    interfaces: Provider and converter protocols
    manager: Sync manager with all sync modes

Example:
    from inorbit_connector.waypoint_sync import (
        WaypointSyncConfig,
        WaypointSyncMode,
        InOrbitConfigClient,
        WaypointSyncManager,
        ExternalAnnotationProvider,
        AnnotationConverter,
        SpatialAnnotation,
    )
"""

from inorbit_connector.waypoint_sync.models import (
    ConfigObject,
    ConfigObjectMetadata,
    ConflictResolutionStrategy,
    SpatialAnnotation,
    WaypointAnnotationSpec,
    WaypointData,
    WaypointSyncConfig,
    WaypointSyncMode,
)
from inorbit_connector.waypoint_sync.config_client import InOrbitConfigClient
from inorbit_connector.waypoint_sync.interfaces import (
    AnnotationConverter,
    ExternalAnnotationProvider,
    TExternalPosition,
)
from inorbit_connector.waypoint_sync.manager import WaypointSyncManager

__all__ = [
    # Configuration
    "WaypointSyncConfig",
    "WaypointSyncMode",
    "ConflictResolutionStrategy",
    # Config API base models
    "ConfigObject",
    "ConfigObjectMetadata",
    # SpatialAnnotation models
    "SpatialAnnotation",
    "WaypointAnnotationSpec",
    "WaypointData",
    # Interfaces
    "ExternalAnnotationProvider",
    "AnnotationConverter",
    "TExternalPosition",
    # Client and Manager
    "InOrbitConfigClient",
    "WaypointSyncManager",
]
