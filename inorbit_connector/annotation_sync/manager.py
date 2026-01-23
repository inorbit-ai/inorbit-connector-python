# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Annotation synchronization manager.

This module provides the AnnotationSyncManager class that implements
the core sync logic for two modes:
- external_to_inorbit: External system is source of truth
- inorbit_to_external: InOrbit is source of truth

Terminology:
    - Annotation: InOrbit SpatialAnnotation (kind: SpatialAnnotation)
    - Position: Waypoint/location in the external system
    - External system: Fleet manager or robot software

Connectors use this class by providing implementations of the
ExternalAnnotationProvider and AnnotationConverter interfaces.
"""

import asyncio
import logging
from typing import Generic, Optional

from inorbit_connector.annotation_sync.interfaces import (
    AnnotationConverter,
    ExternalAnnotationProvider,
    TExternalPosition,
)
from inorbit_connector.annotation_sync.models import (
    ANNOTATION_SYNC_ORIGIN_PROPERTY,
    AnnotationSyncConfig,
    AnnotationSyncMode,
)
from inorbit_connector.inorbit import (
    ConfigObjectMetadata,
    InOrbitConfigAPI,
    SpatialAnnotation,
    SpatialAnnotationData,
)


class AnnotationSyncManager(Generic[TExternalPosition]):
    """Annotation synchronization manager.

    Provides the core sync logic for synchronizing positions between
    an external system and InOrbit annotations.

    Requires:
    1. ExternalAnnotationProvider implementation for position CRUD
    2. AnnotationConverter implementation for position ↔ annotation conversion

    The manager handles:
    - Periodic sync execution
    - Two sync modes (external→InOrbit, InOrbit→external)
    - Signature-based ownership filtering
    - Error handling and logging

    Type Parameters:
        TExternalPosition: The external system's position type (Pydantic model)

    Attributes:
        config: Annotation sync configuration
        _inorbit_client: InOrbit Config API client
        _position_provider: External annotation provider
        _converter: Position ↔ annotation converter
        _logger: Logger instance
        _sync_task: Background sync task
        _stop_event: Event to signal sync stop
    """

    def __init__(
        self,
        config: AnnotationSyncConfig,
        inorbit_config_client: InOrbitConfigAPI,
        position_provider: ExternalAnnotationProvider[TExternalPosition],
        annotation_converter: AnnotationConverter[TExternalPosition],
        account_id: Optional[str],
        frame_id: str,
        signature_value: str,
    ):
        """Initialize annotation sync manager.

        Args:
            config: Annotation sync configuration
            inorbit_config_client: InOrbit Config API client
            position_provider: External annotation provider for position CRUD
            annotation_converter: Converter between positions and annotations
            account_id: InOrbit account ID used for annotation scoping
            frame_id: The frame/map ID this manager syncs for
            signature_value: Signature value used to identify owned annotations
        """
        self.config = config
        self._inorbit_client = inorbit_config_client
        self._position_provider = position_provider
        self._converter = annotation_converter
        self._account_id = account_id
        self._frame_id = frame_id
        self._signature_value = signature_value
        self._logger = logging.getLogger(f"{self.__class__.__name__}[{frame_id}]")
        self._sync_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def _get_scope(self) -> str:
        """Get InOrbit scope for annotations.

        Default: tag/{companyId}/{locationId}
        Override for custom scoping logic.

        Returns:
            Scope string for InOrbit Config API

        Raises:
            ValueError: If required IDs are not configured
        """
        if not self._account_id or not self.config.location_id:
            raise ValueError(
                "account_id and location_id are required for annotation sync"
            )
        return f"tag/{self._account_id}/{self.config.location_id}"

    def _data_to_annotation(
        self, data: SpatialAnnotationData, scope: str
    ) -> SpatialAnnotation:
        """Convert SpatialAnnotationData to full SpatialAnnotation.

        Constructs a complete SpatialAnnotation with metadata, apiVersion,
        and kind from the minimal SpatialAnnotationData. Injects the sync
        signature into spec.properties to mark annotations as managed by
        this sync process.

        Args:
            data: SpatialAnnotationData with id and spec
            scope: Scope string for the annotation

        Returns:
            Complete SpatialAnnotation object with signature injected
        """
        # Copy spec and inject signature
        properties = dict(data.spec.properties)
        properties[ANNOTATION_SYNC_ORIGIN_PROPERTY] = self._signature_value
        spec_with_signature = data.spec.model_copy(update={"properties": properties})

        return SpatialAnnotation(
            metadata=ConfigObjectMetadata(id=data.id, scope=scope),
            spec=spec_with_signature,
        )

    def _annotation_to_data(
        self, annotation: SpatialAnnotation
    ) -> SpatialAnnotationData:
        """Convert SpatialAnnotation to SpatialAnnotationData.

        Extracts the essential data (id and spec) from a full
        SpatialAnnotation for use with the converter interface.

        Args:
            annotation: Full SpatialAnnotation object

        Returns:
            SpatialAnnotationData with id and spec
        """
        return SpatialAnnotationData(
            id=annotation.metadata.id,
            spec=annotation.spec,
        )

    def _has_sync_signature(self, annotation: SpatialAnnotation) -> bool:
        """Check if an annotation has the sync ownership signature.

        The signature identifies annotations that were created/managed
        by this sync process. This prevents modification of other annotations
        during synchronization.

        Args:
            annotation: SpatialAnnotation to check

        Returns:
            True if annotation has matching signature
        """
        return (
            annotation.spec.properties.get(ANNOTATION_SYNC_ORIGIN_PROPERTY)
            == self._signature_value
        )

    async def sync_external_to_inorbit(self) -> dict:
        """Sync positions from external system to InOrbit annotations.

        Fetches all positions from the external system, converts them
        to annotations, and synchronizes with InOrbit Config API.

        Only annotations with the sync signature are considered for
        update/delete operations to avoid affecting manually created annotations.

        Returns:
            Sync statistics dict with keys:
            - created: Number of annotations created
            - updated: Number of annotations updated
            - up_to_date: Number of annotations unchanged
            - deleted: Number of annotations deleted
        """
        self._logger.info(
            f"Starting external → InOrbit annotation sync for frame '{self._frame_id}'"
        )

        # Fetch positions from external system for this frame
        positions = await self._position_provider.list_positions(self._frame_id)
        self._logger.debug(
            f"Fetched {len(positions)} positions from external system "
            f"for frame '{self._frame_id}'"
        )

        # Convert to SpatialAnnotationData
        annotation_data_list = [
            self._converter.position_to_annotation(pos, self._frame_id)
            for pos in positions
        ]

        # Convert to full SpatialAnnotation objects with scope
        scope = self._get_scope()
        annotations = [
            self._data_to_annotation(data, scope) for data in annotation_data_list
        ]

        # Synchronize with InOrbit (deletion is handled by synchronize_objects)
        stats = await self._inorbit_client.synchronize_objects(
            scope=scope,
            objects=annotations,
            filter_fn=self._has_sync_signature,
        )

        self._logger.info(
            f"External → InOrbit sync complete: "
            f"{stats['created']} created, {stats['updated']} updated, "
            f"{stats['deleted']} deleted"
        )
        return stats

    async def sync_inorbit_to_external(self) -> dict:
        """Sync annotations from InOrbit to external system positions.

        Fetches all annotations from InOrbit, filters for owned ones,
        converts them to positions, and synchronizes with the external system.

        Only positions derived from owned annotations are managed.
        Manually created positions in the external system are not affected.

        Returns:
            Sync statistics dict with keys:
            - created: Number of positions created
            - updated: Number of positions updated
            - deleted: Number of positions deleted
        """
        self._logger.info(
            f"Starting InOrbit → external annotation sync for frame '{self._frame_id}'"
        )

        # Fetch annotations from InOrbit
        scope = self._get_scope()
        all_annotations = await self._inorbit_client.list_objects(
            kind="SpatialAnnotation", scope=scope
        )
        # Filter for waypoint annotations and validate
        annotations = []
        for ann in all_annotations:
            if ann.kind == "SpatialAnnotation":
                # Convert to dict and check if it's a waypoint
                ann_dict = ann.model_dump()
                if ann_dict.get("spec", {}).get("type") == "waypoint":
                    annotations.append(SpatialAnnotation.model_validate(ann_dict))

        # Filter for owned annotations belonging to this manager's frame_id
        owned_annotations = [
            ann
            for ann in annotations
            if self._has_sync_signature(ann) and ann.spec.frameId == self._frame_id
        ]

        self._logger.debug(
            f"Fetched {len(owned_annotations)} owned annotations from InOrbit "
            f"for frame '{self._frame_id}'"
        )

        # Fetch existing positions from external system for this frame
        positions = await self._position_provider.list_positions(self._frame_id)
        positions_by_id = {
            self._converter.get_position_id(pos): pos for pos in positions
        }

        created = 0
        updated = 0
        deleted = 0

        # Process annotations
        for ann in owned_annotations:
            annotation_data = self._annotation_to_data(ann)
            position = self._converter.annotation_to_position(annotation_data)
            position_id = ann.metadata.id

            if position_id not in positions_by_id:
                # Create new position
                self._logger.debug(f"Creating position {position_id}")
                await self._position_provider.create_position(position)
                created += 1
            else:
                existing = positions_by_id[position_id]
                # Check if update needed
                if self._needs_update(existing, position):
                    self._logger.debug(f"Updating position {position_id}")
                    await self._position_provider.update_position(position_id, position)
                    updated += 1

            # Remove from dict (already processed)
            positions_by_id.pop(position_id, None)

        # Note: We don't delete positions from external system in this mode
        # because we can't track which positions were created by sync
        # without storing metadata in the external system

        self._logger.info(
            f"InOrbit → external sync complete: "
            f"{created} created, {updated} updated, {deleted} deleted"
        )
        return {
            "created": created,
            "updated": updated,
            "deleted": deleted,
        }

    def _needs_update(
        self, existing: TExternalPosition, new: TExternalPosition
    ) -> bool:
        """Check if position needs update.

        Override for custom comparison logic. Default compares
        Pydantic model dumps.

        Args:
            existing: Existing position (BaseModel subclass)
            new: New position data (BaseModel subclass)

        Returns:
            True if update needed
        """
        return existing.model_dump() != new.model_dump()

    async def sync_once(self) -> dict:
        """Execute single sync based on configured mode.

        Returns:
            Sync statistics

        Raises:
            ValueError: If mode is not implemented
        """
        if self.config.mode == AnnotationSyncMode.EXTERNAL_TO_INORBIT:
            return await self.sync_external_to_inorbit()
        elif self.config.mode == AnnotationSyncMode.INORBIT_TO_EXTERNAL:
            return await self.sync_inorbit_to_external()
        else:
            self._logger.warning(f"Sync mode {self.config.mode} not implemented")
            return {}

    async def _periodic_sync_loop(self) -> None:
        """Periodic sync loop task.

        Runs sync_once() at configured intervals until stopped.
        Errors are logged but don't stop the loop.
        """
        while not self._stop_event.is_set():
            try:
                await self.sync_once()
            except Exception as e:
                self._logger.error(f"Annotation sync failed: {e}", exc_info=True)

            # Wait for next sync interval or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.sync_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass  # Timeout means continue to next sync

    def start(self) -> None:
        """Start periodic annotation synchronization.

        Creates a background task that runs sync at configured intervals.
        Does nothing if sync is disabled (enabled=False) or already running.
        """
        if not self.config.enabled:
            self._logger.info("Annotation sync is disabled")
            return

        if self._sync_task is not None and not self._sync_task.done():
            self._logger.warning("Annotation sync already running")
            return

        self._logger.info(
            f"Starting annotation sync in mode: {self.config.mode.value}, "
            f"interval: {self.config.sync_interval_seconds}s"
        )
        self._stop_event.clear()
        self._sync_task = asyncio.create_task(self._periodic_sync_loop())

    async def stop(self) -> None:
        """Stop periodic annotation synchronization.

        Signals the sync loop to stop and waits for completion.
        """
        if self._sync_task is None or self._sync_task.done():
            return

        self._logger.info("Stopping annotation sync")
        self._stop_event.set()
        await self._sync_task
        self._sync_task = None
