# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Annotation synchronization framework for InOrbit connectors.

**Experimental**: This is an experimental feature with partial support in the
InOrbit platform.

This package provides a reusable framework for synchronizing annotations
(currently waypoints) between external systems and InOrbit's Config API.

For InOrbit Config API models and client, see inorbit_connector.inorbit.
"""

from inorbit_connector.annotation_sync.interfaces import (
    AnnotationConverter,
    ExternalAnnotationProvider,
    TExternalPosition,
)
from inorbit_connector.annotation_sync.manager import AnnotationSyncManager
from inorbit_connector.annotation_sync.models import (
    ANNOTATION_SYNC_ORIGIN_PROPERTY,
    AnnotationSyncConfig,
    AnnotationSyncMode,
)

__all__ = [
    # Configuration
    "AnnotationSyncConfig",
    "AnnotationSyncMode",
    "ANNOTATION_SYNC_ORIGIN_PROPERTY",
    # Interfaces
    "ExternalAnnotationProvider",
    "AnnotationConverter",
    "TExternalPosition",
    # Manager
    "AnnotationSyncManager",
]
