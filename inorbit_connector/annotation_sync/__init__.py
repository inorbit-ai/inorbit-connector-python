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
    models: Configuration and data models (AnnotationSyncConfig, SpatialAnnotation)
    interfaces: Provider and converter protocols
    manager: Sync manager with all sync modes

Example:
    from inorbit_connector.waypoint_sync import (
        AnnotationSyncConfig,
        AnnotationSyncMode,
        InOrbitConfigClient,
        AnnotationSyncManager,
        ExternalAnnotationProvider,
        AnnotationConverter,
        SpatialAnnotation,
    )
"""

from inorbit_connector.annotation_sync.models import (
    AnnotationSyncConfig,
    AnnotationSyncMode,
    ConfigObject,
    ConfigObjectMetadata,
    SpatialAnnotation,
    SpatialAnnotationData,
    WaypointAnnotationSpec,
    WaypointData,
)
from inorbit_connector.annotation_sync.config_client import InOrbitConfigClient
from inorbit_connector.annotation_sync.interfaces import (
    AnnotationConverter,
    ExternalAnnotationProvider,
    TExternalPosition,
)
from inorbit_connector.annotation_sync.manager import AnnotationSyncManager

__all__ = [
    # Configuration
    "AnnotationSyncConfig",
    "AnnotationSyncMode",
    # Config API base models
    "ConfigObject",
    "ConfigObjectMetadata",
    # SpatialAnnotation models
    "SpatialAnnotation",
    "SpatialAnnotationData",
    "WaypointAnnotationSpec",
    "WaypointData",
    # Interfaces
    "ExternalAnnotationProvider",
    "AnnotationConverter",
    "TExternalPosition",
    # Client and Manager
    "InOrbitConfigClient",
    "AnnotationSyncManager",
]
