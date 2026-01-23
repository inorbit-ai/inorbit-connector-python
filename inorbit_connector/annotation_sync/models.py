# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Annotation synchronization configuration models.

This module provides configuration models for annotation synchronization.
For InOrbit Config API models and SpatialAnnotation, see inorbit_connector.inorbit.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

ANNOTATION_SYNC_ORIGIN_PROPERTY = "syncOrigin"


class AnnotationSyncMode(str, Enum):
    """Synchronization modes for annotation synchronization.

    Attributes:
        EXTERNAL_TO_INORBIT: Sync from external system to InOrbit
            (external system is source of truth)
        INORBIT_TO_EXTERNAL: Sync from InOrbit to external system
            (InOrbit is source of truth)
    """

    EXTERNAL_TO_INORBIT = "external_to_inorbit"
    INORBIT_TO_EXTERNAL = "inorbit_to_external"


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
        mode: Synchronization mode (default: EXTERNAL_TO_INORBIT)
        sync_interval_seconds: Interval between syncs in seconds
        location_id: Location/tag ID for annotation scope in InOrbit
    """

    enabled: bool = False
    mode: AnnotationSyncMode = AnnotationSyncMode.EXTERNAL_TO_INORBIT
    sync_interval_seconds: int = Field(default=300, gt=0)

    # InOrbit Config API settings
    location_id: Optional[str] = None
