---
title: "Annotation Synchronization"
description: "Guide for implementing annotation synchronization in connectors"
---

> **Note:** Annotation synchronization is currently an experimental feature with partial support in the InOrbit platform.

This guide explains how to enable and configure annotation synchronization between your external system and InOrbit.

## Terminology

- **Annotation**: An InOrbit `SpatialAnnotation` object. Currently, only waypoint annotations are supported.
- **Position**: A waypoint/location in the external system.
- **External system**: The software the connector interacts with (fleet manager, robot software).

## Overview

Annotation synchronization keeps positions/waypoints in sync between your external system and the InOrbit platform.

## Sync Modes

| Mode                  | Direction          | Description                        |
| --------------------- | ------------------ | ---------------------------------- |
| `external_to_inorbit` | External → InOrbit | External system is source of truth |
| `inorbit_to_external` | InOrbit → External | InOrbit is source of truth         |

## Configuration

Annotation synchronization is configured via the connector YAML configuration file:

```yaml
...
# Annotation synchronization
annotation_sync:
  enabled: true
  mode: external_to_inorbit
  sync_interval_seconds: 300

  # InOrbit scope settings
  location_id: "location-tag-id"
...
```

The connector automatically starts annotation synchronization for each frame_id as robot poses are published, enabling fleet integrations with
robots operating on multiple maps.

### Configuration Fields

| Field                   | Required | Default               | Description                 |
| ----------------------- | -------- | --------------------- | --------------------------- |
| `enabled`               | No       | `false`               | Enable annotation sync      |
| `mode`                  | No       | `external_to_inorbit` | Sync mode                   |
| `sync_interval_seconds` | No       | `300`                 | Interval between syncs      |
| `location_id`           | Yes*     | -                     | Location tag ID for scoping |

## Ownership Signatures

The sync uses **signature properties** to identify annotations it manages:

The ownership signature uses a fixed property name (`syncOrigin`) and the `connector_type` as value.

This adds a property to each synchronized annotation:

```json
{
  "spec": {
    "properties": {
        "syncOrigin": "my-connector"
    }
  }
}
```

This prevents the deletion of manually created annotations and enables multiple connectors to manage separate annotation sets.

## Usage

1. Define a Pydantic model for your external positions. This is required for type-safe serialization via `model_dump()` and automatic change detection in sync operations.

```python
from pydantic import BaseModel

class MyPosition(BaseModel):
    """External system position model."""
    id: str
    name: str
    x: float
    y: float
    orientation: float
```

2. Implement the `ExternalAnnotationProvider` protocol.

```python
class MyPositionProvider:
    """Provides CRUD operations for your external system's positions."""

    async def list_positions(self, frame_id: str) -> list[MyPosition]:
        """Fetch positions for the given frame_id (map).

        The framework calls this method with the frame_id it's syncing for.
        Filter positions to only return those on the specified map.
        """
        data = await self._client.get_positions(map_id=frame_id)
        return [MyPosition.model_validate(p) for p in data]

    async def create_position(self, position: MyPosition) -> None:
        """Create a new position."""
        await self._client.create_position(position.model_dump())

    async def update_position(
        self, position_id: str, position: MyPosition
    ) -> None:
        """Update existing position."""
        await self._client.update_position(
            position_id, position.model_dump()
        )

    async def delete_position(self, position_id: str) -> None:
        """Delete a position."""
        await self._client.delete_position(position_id)
```

3. Implement the `AnnotationConverter` protocol.

```python
class MyAnnotationConverter:
    """Converts between positions and waypoint annotations."""

    def position_to_annotation(
        self, position: MyPosition, frame_id: str
    ) -> SpatialAnnotationData:
        """Convert position to SpatialAnnotationData.

        Args:
            position: The external position to convert
            frame_id: The frame/map ID for this annotation (provided by framework)
        """
        return SpatialAnnotationData(
            id=position.id,
            spec=WaypointAnnotationSpec(
                frameId=frame_id,
                label=position.name,
                data=WaypointData(
                    x=position.x,
                    y=position.y,
                    theta=position.orientation
                ),
                properties={}
            )
        )

    def annotation_to_position(
        self, annotation_data: SpatialAnnotationData
    ) -> MyPosition:
        """Convert SpatialAnnotationData to position."""
        return MyPosition(
            id=annotation_data.id,
            name=annotation_data.spec.label,
            x=annotation_data.spec.data.x,
            y=annotation_data.spec.data.y,
            orientation=annotation_data.spec.data.theta
        )

    def get_position_id(self, position: MyPosition) -> str:
        """Extract position ID."""
        return position.id
```

4. Register the provider and converter with the connector.

```python
class MyConnector(FleetConnector):
    def __init__(self, config):
        super().__init__(config)

        # Register provider and converter
        self.register_annotation_sync(MyPositionProvider(), MyAnnotationConverter())
```

## Troubleshooting

1. **Check configuration**: Ensure `enabled: true` and valid `mode`
2. **Verify API key**: Must have permissions for Config API
3. **Check auth method**: The Config API requires an `api_key`, not an `inorbit_robot_key`
4. **Check scope**: Ensure `account_id` and `location_id` are correct

## See Also

- [Annotation Sync API Reference](../specification/annotation-sync)
- [FleetConnector Specification](../specification/connector)
- [Configuration Guide](../configuration)
