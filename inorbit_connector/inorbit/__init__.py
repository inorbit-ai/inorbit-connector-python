# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""InOrbit API module.

This module provides models and clients for interacting with InOrbit's APIs,
including the Config API for managing configuration objects.

For more information, see:
https://developer.inorbit.ai/docs#configuration-management
"""

from inorbit_connector.inorbit.config_api import InOrbitConfigAPI
from inorbit_connector.inorbit.models import (
    ConfigObject,
    ConfigObjectMetadata,
    SpatialAnnotation,
    SpatialAnnotationData,
    WaypointAnnotationSpec,
    WaypointData,
)

__all__ = [
    # Config API models
    "ConfigObject",
    "ConfigObjectMetadata",
    # SpatialAnnotation models
    "SpatialAnnotation",
    "SpatialAnnotationData",
    "WaypointAnnotationSpec",
    "WaypointData",
    # Client
    "InOrbitConfigAPI",
]
