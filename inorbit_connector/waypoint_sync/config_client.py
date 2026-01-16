# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""InOrbit Configuration API client.

This module provides a client for interacting with InOrbit's Config API,
enabling CRUD operations on configuration objects like SpatialAnnotations.

The client handles:
    - Listing config objects by kind and scope
    - Creating/updating config objects via apply
    - Synchronizing config objects with ownership-based filtering

This module is designed to be self-contained and could be extracted
to a separate package (e.g., inorbit-config-api) in the future.
"""

import logging
from typing import Callable, Optional

import httpx

from inorbit_connector.waypoint_sync.models import SpatialAnnotation


class InOrbitConfigClient:
    """Client for InOrbit Configuration API.

    Provides methods to interact with InOrbit's Config API for managing
    spatial annotations and other configuration objects.

    Attributes:
        _base_url: InOrbit API base URL
        _api_key: InOrbit API key
        _timeout: Request timeout in seconds
        _client: Async HTTP client
        _logger: Logger instance
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
    ):
        """Initialize InOrbit Config API client.

        Args:
            base_url: InOrbit API base URL (e.g., https://api.inorbit.ai)
            api_key: InOrbit API key
            timeout: Request timeout in seconds
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.info(
            f"Initializing InOrbit Config API client with base URL: {self._base_url}, API key: {api_key}, timeout: {timeout}"
        )
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "x-auth-inorbit-app-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def list_annotations(
        self,
        scope: str,
        format: str = "full",
    ) -> list[SpatialAnnotation]:
        """Retrieve spatial annotations from InOrbit.

        Args:
            scope: Object scope (e.g., "tag/{companyId}/{locationId}")
            format: Response format ("full" or "summary")

        Returns:
            List of SpatialAnnotation objects

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        self._logger.info(f"Listing annotations for scope: {scope}, format: {format}")
        response = await self._client.get(
            "/configuration/list",
            params={
                "kind": "SpatialAnnotation",
                "scope": scope,
                "format": format,
            },
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        waypoint_items = [
            item for item in items if item.get("spec", {}).get("type") == "waypoint"
        ]
        return [SpatialAnnotation.model_validate(item) for item in waypoint_items]

    async def apply_annotation(
        self, annotation: SpatialAnnotation
    ) -> SpatialAnnotation:
        """Apply (create or update) a spatial annotation.

        Args:
            annotation: SpatialAnnotation to create or update

        Returns:
            Applied annotation from the API response

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        response = await self._client.post(
            "/configuration/apply",
            json=annotation.model_dump(mode="json"),
        )
        # self._logger.debug(f"Applying annotation: {annotation.model_dump(mode='json')}")
        # import yaml

        # print(yaml.dump(annotation.model_dump(mode="json")))

        response.raise_for_status()
        return annotation

    async def delete_annotation(
        self,
        scope: str,
        annotation_id: str,
    ) -> None:
        """Delete an annotation.

        Args:
            scope: Annotation scope
            annotation_id: Annotation ID

        Note:
            This method is a placeholder. The actual deletion mechanism
            depends on the InOrbit API implementation.
        """
        self._logger.warning(
            f"Delete operation for annotation {annotation_id} not yet implemented"
        )

    async def synchronize_annotations(
        self,
        scope: str,
        annotations: list[SpatialAnnotation],
        filter_fn: Optional[Callable[[SpatialAnnotation], bool]] = None,
    ) -> dict:
        """Synchronize annotations with InOrbit.

        Compares local annotations with remote and:
        - Creates new annotations
        - Updates changed annotations
        - Identifies annotations to delete (filtered by ownership)

        Args:
            scope: Annotation scope (e.g., "tag/{companyId}/{locationId}")
            annotations: List of SpatialAnnotation objects to sync
            filter_fn: Optional filter for existing annotations.
                Only annotations passing this filter will be considered for
                update/delete operations. This prevents deletion of annotations
                created by other sources.

        Returns:
            Sync statistics with keys:
            - created: Number of annotations created
            - updated: Number of annotations updated
            - up_to_date: Number of annotations unchanged
            - to_delete: List of annotation IDs to delete
            - to_delete_count: Number of annotations to delete

        Raises:
            ValueError: If annotation has mismatched scope
            httpx.HTTPStatusError: If any API request fails
        """
        # Inject scope into metadata
        for ann in annotations:
            if ann.metadata.scope is None:
                ann.metadata.scope = scope
            elif ann.metadata.scope != scope:
                raise ValueError(
                    f"Annotation {ann.metadata.id} has scope "
                    f"{ann.metadata.scope} but expected {scope}"
                )

        # Fetch existing annotations
        existing_annotations = await self.list_annotations(scope)
        if filter_fn:
            existing_annotations = [
                ann for ann in existing_annotations if filter_fn(ann)
            ]

        existing_by_id = {ann.metadata.id: ann for ann in existing_annotations}

        created = 0
        updated = 0
        up_to_date = 0

        # Process annotations
        for ann in annotations:
            ann_id = ann.metadata.id
            existing = existing_by_id.get(ann_id)

            if existing is None:
                # Create new annotation
                self._logger.debug(f"Creating annotation {ann_id}")
                await self.apply_annotation(ann)
                created += 1
            elif existing.model_dump() != ann.model_dump():
                # Update changed annotation
                self._logger.debug(f"Updating annotation {ann_id}")
                await self.apply_annotation(ann)
                updated += 1
            else:
                # Annotation unchanged
                up_to_date += 1

            # Remove from existing dict (already processed)
            existing_by_id.pop(ann_id, None)

        # Remaining annotations should be deleted
        to_delete = list(existing_by_id.keys())

        self._logger.info(
            f"Sync complete: {created} created, {updated} updated, "
            f"{up_to_date} up to date, {len(to_delete)} to delete"
        )

        return {
            "created": created,
            "updated": updated,
            "up_to_date": up_to_date,
            "to_delete": to_delete,
            "to_delete_count": len(to_delete),
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "InOrbitConfigClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
