# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Annotation synchronization manager.

This module provides the WaypointSyncManager class that implements
the core sync logic for all three modes:
- external_to_inorbit: External system is source of truth
- inorbit_to_external: InOrbit is source of truth
- bidirectional: Two-way sync with conflict resolution

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

from inorbit_connector.waypoint_sync.config_client import InOrbitConfigClient
from inorbit_connector.waypoint_sync.models import (
    ANNOTATION_SYNC_ORIGIN_PROPERTY,
    ConflictResolutionStrategy,
    SpatialAnnotation,
    WaypointSyncConfig,
    WaypointSyncMode,
)
from inorbit_connector.waypoint_sync.interfaces import (
    AnnotationConverter,
    ExternalAnnotationProvider,
    TExternalPosition,
)


class WaypointSyncManager(Generic[TExternalPosition]):
    """Waypoint annotation synchronization manager.

    Provides the core sync logic for synchronizing positions between
    an external system and InOrbit annotations.

    Requires:
    1. ExternalAnnotationProvider implementation for position CRUD
    2. AnnotationConverter implementation for position ↔ annotation conversion

    The manager handles:
    - Periodic sync execution
    - All three sync modes (external→InOrbit, InOrbit→external, bidirectional)
    - Conflict resolution for bidirectional sync
    - Signature-based ownership filtering
    - Error handling and logging

    Type Parameters:
        TExternalPosition: The external system's position type (Pydantic model)

    Attributes:
        config: Waypoint sync configuration
        _inorbit_client: InOrbit Config API client
        _position_provider: External annotation provider
        _converter: Position ↔ annotation converter
        _logger: Logger instance
        _sync_task: Background sync task
        _stop_event: Event to signal sync stop
    """

    def __init__(
        self,
        config: WaypointSyncConfig,
        inorbit_config_client: InOrbitConfigClient,
        position_provider: ExternalAnnotationProvider[TExternalPosition],
        annotation_converter: AnnotationConverter[TExternalPosition],
        account_id: Optional[str],
        frame_id: str,
        signature_value: str,
    ):
        """Initialize waypoint sync manager.

        Args:
            config: Waypoint sync configuration
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

    def _get_ownership_filter(self):
        """Create filter function for annotations owned by this sync.

        Returns:
            Filter function that returns True for owned annotations
        """

        def filter_fn(annotation: SpatialAnnotation) -> bool:
            return self._converter.has_sync_signature(
                annotation,
                ANNOTATION_SYNC_ORIGIN_PROPERTY,
                self._signature_value,
            )

        return filter_fn

    async def sync_external_to_inorbit(self) -> dict:
        """Sync positions from external system to InOrbit annotations.

        Fetches all positions from the external system, converts them
        to waypoint annotations, and synchronizes with InOrbit Config API.

        Only annotations with the sync signature are considered for
        update/delete operations to avoid affecting manually created annotations.

        Returns:
            Sync statistics dict with keys:
            - created: Number of annotations created
            - updated: Number of annotations updated
            - up_to_date: Number of annotations unchanged
            - to_delete_count: Number of annotations to delete
        """
        self._logger.info(
            f"Starting external → InOrbit annotation sync for frame '{self._frame_id}'"
        )

        # Fetch positions from external system for this frame
        positions = await self._position_provider.list_positions(self._frame_id)
        self._logger.debug(
            f"Fetched {len(positions)} positions from external system for frame '{self._frame_id}'"
        )

        # Convert to InOrbit waypoint annotations
        annotations = [
            self._converter.position_to_annotation(pos, self._frame_id)
            for pos in positions
        ]

        # Synchronize with InOrbit
        scope = self._get_scope()
        stats = await self._inorbit_client.synchronize_annotations(
            scope=scope,
            annotations=annotations,
            filter_fn=self._get_ownership_filter(),
        )

        self._logger.info(
            f"External → InOrbit sync complete: "
            f"{stats['created']} created, {stats['updated']} updated, "
            f"{stats['to_delete_count']} to delete"
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
        annotations = await self._inorbit_client.list_annotations(scope)

        # Filter for owned waypoint annotations only
        owned_annotations = [
            ann
            for ann in annotations
            if ann.spec.type == "waypoint"
            and self._converter.has_sync_signature(
                ann,
                ANNOTATION_SYNC_ORIGIN_PROPERTY,
                self._signature_value,
            )
        ]
        self._logger.debug(
            f"Fetched {len(owned_annotations)} owned annotations from InOrbit"
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
            position = self._converter.annotation_to_position(ann)
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

    def _needs_update(self, existing: TExternalPosition, new: TExternalPosition) -> bool:
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

    async def sync_bidirectional(self) -> dict:
        """Bidirectional sync with conflict resolution.

        Fetches data from both systems and syncs:
        - Positions only in external → create annotation in InOrbit
        - Annotations only in InOrbit → create position in external
        - Exists in both → apply conflict resolution strategy

        Returns:
            Combined sync statistics dict with keys:
            - external_created, external_updated, external_deleted
            - inorbit_created, inorbit_updated
            - conflicts_resolved
        """
        self._logger.info(
            f"Starting bidirectional annotation sync for frame '{self._frame_id}'"
        )

        # Fetch from both systems
        positions = await self._position_provider.list_positions(self._frame_id)
        scope = self._get_scope()
        annotations = await self._inorbit_client.list_annotations(scope)

        # Filter owned waypoint annotations
        owned_annotations = [
            ann
            for ann in annotations
            if ann.spec.type == "waypoint"
            and self._converter.has_sync_signature(
                ann,
                ANNOTATION_SYNC_ORIGIN_PROPERTY,
                self._signature_value,
            )
        ]

        # Build ID mappings
        positions_by_id = {
            self._converter.get_position_id(pos): pos for pos in positions
        }
        annotations_by_id = {ann.metadata.id: ann for ann in owned_annotations}

        # Combine all IDs
        all_ids = set(positions_by_id.keys()) | set(annotations_by_id.keys())

        stats = {
            "external_created": 0,
            "external_updated": 0,
            "external_deleted": 0,
            "inorbit_created": 0,
            "inorbit_updated": 0,
            "conflicts_resolved": 0,
        }

        for item_id in all_ids:
            has_position = item_id in positions_by_id
            has_annotation = item_id in annotations_by_id

            if has_position and not has_annotation:
                # Exists only in external → sync to InOrbit
                position = positions_by_id[item_id]
                annotation = self._converter.position_to_annotation(
                    position, self._frame_id
                )
                await self._inorbit_client.apply_annotation(annotation)
                stats["inorbit_created"] += 1

            elif has_annotation and not has_position:
                # Exists only in InOrbit → sync to external
                annotation = annotations_by_id[item_id]
                position = self._converter.annotation_to_position(annotation)
                await self._position_provider.create_position(position)
                stats["external_created"] += 1

            else:
                # Exists in both → resolve conflict
                position = positions_by_id[item_id]
                annotation = annotations_by_id[item_id]

                # Apply conflict resolution strategy
                winner = self._resolve_conflict(position, annotation)

                if winner == "external":
                    # Update InOrbit with external version
                    new_annotation = self._converter.position_to_annotation(
                        position, self._frame_id
                    )
                    await self._inorbit_client.apply_annotation(new_annotation)
                    stats["inorbit_updated"] += 1
                elif winner == "inorbit":
                    # Update external with InOrbit version
                    new_position = self._converter.annotation_to_position(annotation)
                    await self._position_provider.update_position(
                        item_id, new_position
                    )
                    stats["external_updated"] += 1

                stats["conflicts_resolved"] += 1

        self._logger.info(
            f"Bidirectional sync complete: "
            f"InOrbit {stats['inorbit_created']}c/{stats['inorbit_updated']}u, "
            f"External {stats['external_created']}c/{stats['external_updated']}u, "
            f"{stats['conflicts_resolved']} conflicts resolved"
        )
        return stats

    def _resolve_conflict(
        self, position: TExternalPosition, annotation: SpatialAnnotation
    ) -> str:
        """Resolve conflict between position and annotation.

        Uses the configured conflict resolution strategy.

        Args:
            position: External position
            annotation: InOrbit annotation

        Returns:
            "external" or "inorbit" indicating which version wins
        """
        strategy = self.config.conflict_strategy

        if strategy == ConflictResolutionStrategy.EXTERNAL_WINS:
            return "external"
        elif strategy == ConflictResolutionStrategy.INORBIT_WINS:
            return "inorbit"
        elif strategy == ConflictResolutionStrategy.NEWEST_WINS:
            # Compare timestamps (if available in properties)
            pos_data = position.model_dump()
            pos_timestamp = pos_data.get("properties", {}).get("last_sync")
            ann_timestamp = annotation.spec.properties.get("last_sync")

            if pos_timestamp and ann_timestamp:
                return "external" if pos_timestamp > ann_timestamp else "inorbit"
            # Fallback to external wins if timestamps not available
            return "external"

        return "external"

    async def sync_once(self) -> dict:
        """Execute single sync based on configured mode.

        Returns:
            Sync statistics

        Raises:
            ValueError: If mode is not implemented
        """
        if self.config.mode == WaypointSyncMode.EXTERNAL_TO_INORBIT:
            return await self.sync_external_to_inorbit()
        elif self.config.mode == WaypointSyncMode.INORBIT_TO_EXTERNAL:
            return await self.sync_inorbit_to_external()
        elif self.config.mode == WaypointSyncMode.BIDIRECTIONAL:
            return await self.sync_bidirectional()
        elif self.config.mode == WaypointSyncMode.DISABLED:
            self._logger.debug("Sync mode is DISABLED, skipping")
            return {}
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
        Does nothing if sync mode is DISABLED or already running.
        """
        if self.config.mode == WaypointSyncMode.DISABLED:
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
