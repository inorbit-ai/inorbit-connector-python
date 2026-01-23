# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""InOrbit Configuration API client.

This module provides a client for interacting with InOrbit's Config API,
enabling CRUD operations on configuration objects.
"""

import logging
from typing import Callable, Literal, Optional

import httpx

from inorbit_connector.inorbit.models import ConfigObject


class InOrbitConfigAPI:
    """Client for InOrbit Configuration API.

    Provides methods to interact with InOrbit's Config API for managing
    configuration objects.

    See https://developer.inorbit.ai/docs#configuration-management and
    https://api.inorbit.ai/docs/index.html#tag/configAPI for detailed API documentation.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
    ):
        """Initialize InOrbit Config API client.

        Args:
            base_url: InOrbit API base URL
            api_key: InOrbit API key
            timeout: Request timeout in seconds
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "x-auth-inorbit-app-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def list_objects(
        self,
        kind: str,
        scope: str,
        format: Literal["full", "short"] = "full",
    ) -> list[ConfigObject]:
        """Retrieve config objects from InOrbit.

        Args:
            kind: Object kind (e.g., "SpatialAnnotation")
            scope: Object scope (e.g., "tag/{companyId}/{locationId}")
            format: Response format ("full" or "short")

        Returns:
            List of ConfigObject objects

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        self._logger.debug(
            f"Listing {kind} objects for scope: {scope}, format: {format}"
        )
        response = await self._client.get(
            "/configuration/list",
            params={
                "kind": kind,
                "scope": scope,
                "format": format,
            },
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        return [ConfigObject.model_validate(item) for item in items]

    async def apply_object(self, obj: ConfigObject) -> ConfigObject:
        """Apply (create or update) a config object.

        Args:
            obj: ConfigObject to create or update

        Returns:
            Applied object

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        response = await self._client.post(
            "/configuration/apply",
            json=obj.model_dump(mode="json"),
        )
        response.raise_for_status()
        return obj

    async def delete_object(self, obj: ConfigObject) -> None:
        """Delete a config object.

        Args:
            obj: ConfigObject to delete

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        response = await self._client.post(
            "/configuration/clear",
            json=obj.model_dump(mode="json"),
        )
        response.raise_for_status()

    async def synchronize_objects(
        self,
        scope: str,
        objects: list[ConfigObject],
        filter_fn: Optional[Callable[[ConfigObject], bool]] = None,
    ) -> dict:
        """Synchronize config objects with InOrbit.

        Compares local objects with remote and:
        - Creates new objects
        - Updates changed objects
        - Deletes objects that no longer exist locally (filtered by ownership)

        Args:
            scope: Object scope (e.g., "tag/{companyId}/{locationId}")
            objects: List of ConfigObject objects to sync
            filter_fn: Optional filter for existing objects.
                Only objects passing this filter will be considered for
                update/delete operations.

        Returns:
            Sync statistics with keys:
            - created: Number of objects created
            - updated: Number of objects updated
            - up_to_date: Number of objects unchanged
            - deleted: Number of objects deleted

        Raises:
            ValueError: If object has mismatched scope or if objects have mixed kinds
            httpx.HTTPStatusError: If any API request fails
        """
        if not objects:
            return {
                "created": 0,
                "updated": 0,
                "up_to_date": 0,
                "deleted": 0,
            }

        kind = objects[0].kind

        # Validate all objects have the same kind
        for obj in objects:
            if obj.kind != kind:
                raise ValueError(
                    f"Object {obj.metadata.id} has kind {obj.kind} "
                    f"but expected {kind}. All objects must have the same kind."
                )

        # Inject scope into metadata
        for obj in objects:
            if obj.metadata.scope is None:
                obj.metadata.scope = scope
            elif obj.metadata.scope != scope:
                raise ValueError(
                    f"Object {obj.metadata.id} has scope "
                    f"{obj.metadata.scope} but expected {scope}"
                )

        # Fetch existing objects
        existing_objects = await self.list_objects(kind, scope)
        if filter_fn:
            existing_objects = [obj for obj in existing_objects if filter_fn(obj)]

        existing_by_id = {obj.metadata.id: obj for obj in existing_objects}

        created = 0
        updated = 0
        up_to_date = 0

        # Process objects
        for obj in objects:
            obj_id = obj.metadata.id
            existing = existing_by_id.get(obj_id)

            if existing is None:
                # Create new object
                self._logger.debug(f"Creating {kind} {obj_id}")
                await self.apply_object(obj)
                created += 1
            elif existing.model_dump() != obj.model_dump():
                # Update changed object
                self._logger.debug(f"Updating {kind} {obj_id}")
                await self.apply_object(obj)
                updated += 1
            else:
                # Object unchanged
                up_to_date += 1

            # Remove from existing dict (already processed)
            existing_by_id.pop(obj_id, None)

        # Delete remaining objects
        deleted = 0
        for obj_id in existing_by_id.keys():
            obj = existing_by_id[obj_id]
            self._logger.debug(f"Deleting {kind} {obj_id}")
            await self.delete_object(obj)
            deleted += 1

        self._logger.info(
            f"Sync complete: {created} created, {updated} updated, "
            f"{up_to_date} up to date, {deleted} deleted"
        )

        return {
            "created": created,
            "updated": updated,
            "up_to_date": up_to_date,
            "deleted": deleted,
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "InOrbitConfigAPI":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
