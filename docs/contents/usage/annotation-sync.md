---
title: "Annotation Synchronization"
description: "Guide for implementing annotation synchronization in connectors"
---

> **Note:** Annotation synchronization is currently an experimental feature with partial support in the InOrbit platform.

This guide explains how to enable and configure annotation synchronization between your external system and InOrbit.

## Terminology

- **Annotation**: An InOrbit `SpatialAnnotation` object. Currently, we support waypoint annotations (`spec.type == "waypoint"`).
- **Position**: A waypoint/location in the external system.
- **External system**: Fleet manager or robot software the connector integrates with.

## Overview

Annotation synchronization keeps positions/waypoints in sync between:
- Your **external system** (e.g., MiR Fleet, Bluebotics, robot software)
- **InOrbit's Config API** (SpatialAnnotation objects)

## Sync Modes

| Mode | Direction | Description |
|------|-----------|-------------|
| `external_to_inorbit` | External → InOrbit | External system is source of truth |
| `inorbit_to_external` | InOrbit → External | InOrbit is source of truth |

## Configuration

Annotation sync is configured at the `ConnectorConfig` level:

```yaml
# connector-config.yaml

api_key: ${INORBIT_API_KEY}
rest_api_url: ${INORBIT_REST_API_URL}
account_id: ${INORBIT_ACCOUNT_ID}
connector_type: my_connector

# Annotation synchronization (framework-level feature)
annotation_sync:
  enabled: true
  mode: external_to_inorbit
  sync_interval_seconds: 300

  # InOrbit scope settings
  location_id: "facility-location-id"

# Connector-specific settings
connector_config:
  host: 192.168.1.50
```

**Note**: `frame_id` is not configured statically. The framework automatically starts
sync for each frame_id as robot poses are published, supporting fleet connectors with
robots on multiple maps.

`rest_api_url` points to the InOrbit REST API used by the Config API. It defaults to
the edge SDK's REST API base URL and can be overridden with `INORBIT_REST_API_URL`.

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `enabled` | No | `false` | Enable annotation sync |
| `mode` | No | `external_to_inorbit` | Sync mode |
| `sync_interval_seconds` | No | `300` | Interval between syncs |
| `location_id` | Yes* | - | Location tag ID for scoping |

*Required when `enabled` is `true`. `account_id` must also be set in `ConnectorConfig`.

**Dynamic frame_id**: The framework automatically detects new frame_ids when robot poses
are published and starts sync for each unique frame. This supports fleet connectors
where robots operate on multiple maps.

## Choosing the Right Mode

### External to InOrbit (`external_to_inorbit`)

Use when your external system is the source of truth for positions.

**Behavior**:
- Fetches all positions from external system
- Creates/updates matching waypoint annotations in InOrbit
- Marks stale annotations for deletion

**Best for**:
- Operators who manage waypoints in the external system's UI
- Systems where the external system has authoritative position data

### InOrbit to External (`inorbit_to_external`)

Use when InOrbit is the source of truth for waypoints.

**Behavior**:
- Fetches waypoint annotations from InOrbit Config API
- Creates/updates matching positions in external system
- Only manages positions derived from owned annotations

**Best for**:
- Operators who manage waypoints via InOrbit's map editor
- Centralized waypoint management

## Ownership Signatures

The sync uses **signature properties** to identify annotations it manages:

The ownership signature uses a fixed property name (`syncOrigin`) and the connector type as value:

```yaml
connector_type: my-connector
```

This adds a property to each synced annotation:

```json
{
  "spec": {
    "properties": {
        "syncOrigin": "my-connector"
    }
  }
}
```

**Why this matters**:
- Prevents deletion of manually created annotations
- Enables multiple connectors to manage separate annotation sets
- Provides clear ownership tracking

## Implementing in Your Connector

### 1. Define Position Model (Pydantic BaseModel)

External positions **must** be Pydantic `BaseModel` subclasses. This is required for:
- Type-safe serialization via `model_dump()`
- Automatic change detection in sync operations

```python
from pydantic import BaseModel

class MyPosition(BaseModel):
    """External system position model (must inherit from BaseModel)."""
    id: str
    name: str
    x: float
    y: float
    orientation: float
```

### 2. Implement ExternalAnnotationProvider

Provides CRUD operations for your external system's positions:

```python
class MyPositionProvider:
    """Implements ExternalAnnotationProvider protocol."""

    def __init__(self, client):
        self._client = client

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

### 3. Implement AnnotationConverter

Converts between positions and waypoint annotations:

```python
from inorbit_connector.annotation_sync.models import (
    SpatialAnnotationData,
    WaypointAnnotationSpec,
    WaypointData,
)

class MyAnnotationConverter:
    """Implements AnnotationConverter protocol."""

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

### 4. Framework Creates Sync Managers Per Frame

The framework automatically creates `AnnotationSyncManager` instances for each unique
`frame_id` as robot poses are published. You don't need to create managers directly.

**How it works**:
1. When `publish_robot_pose(robot_id, x, y, yaw, frame_id)` is called
2. If `frame_id` is new (not seen before), the framework creates a sync manager for it
3. The manager calls `provider.list_positions(frame_id)` to get positions for that map
4. The manager calls `converter.position_to_annotation(position, frame_id)` to convert

### 5. Integrate with Connector

Register the implementations and let the framework manage initialization and start/stop:

```python
class MyConnector(FleetConnector):
    def __init__(self, config):
        super().__init__(config)

        # Create provider and converter (frame_id is handled dynamically)
        provider = MyPositionProvider(self._my_client)
        converter = MyAnnotationConverter()

        # Register with framework - sync starts automatically per frame_id
        self.register_annotation_sync(provider, converter)
```

**Note**: Always register the provider and converter. The framework checks
`annotation_sync.enabled` to decide whether to actually run the sync.

## Monitoring Sync Operations

The sync manager logs operations at various levels:

| Level | What's Logged |
|-------|---------------|
| INFO | Sync start/complete, counts |
| DEBUG | Individual create/update/delete |
| WARNING | Skipped operations, missing data |
| ERROR | Sync failures with stack traces |

Example log output:

```
INFO - Starting external → InOrbit annotation sync
DEBUG - Fetched 42 positions from external system
INFO - Sync complete: 5 created, 3 updated, 34 up to date, 0 to delete
```

## Troubleshooting

### Annotations not syncing

1. **Check configuration**: Ensure `enabled: true` and valid `mode`
2. **Verify API key**: Must have permissions for Config API
3. **Check auth method**: Config API requires `api_key` (robot keys are not supported)
4. **Check scope**: Ensure `account_id` and `location_id` are correct

### Manual annotations being deleted

Check your ownership signature:
- Manually created annotations won't have the signature property
- Only annotations with matching signature are managed by sync

## See Also

- [Annotation Sync API Reference](../specification/annotation-sync)
- [FleetConnector Specification](../specification/connector)
- [Configuration Guide](../configuration)
