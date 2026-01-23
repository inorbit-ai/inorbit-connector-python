---
title: "Annotation Synchronization"
description: "API specification for synchronizing annotations between external systems and InOrbit"
---

> **Note:** Annotation synchronization is currently an experimental feature with partial support in the InOrbit platform.

The annotation synchronization framework enables connectors to synchronize waypoint annotations between external systems and InOrbit's Config API.

For Config API models and client, see [Config API](config-api).

## Terminology

- **Annotation**: An InOrbit `SpatialAnnotation` object. Currently, only waypoint annotations are supported.
- **Position**: A waypoint/location in the external system.
- **External system**: The software the connector interacts with (fleet manager, robot software).

## AnnotationSyncConfig

Configuration for annotation synchronization:

```python
from inorbit_connector.annotation_sync import AnnotationSyncConfig, AnnotationSyncMode

config = AnnotationSyncConfig(
    enabled=True,
    mode=AnnotationSyncMode.EXTERNAL_TO_INORBIT,
    sync_interval_seconds=300,
    location_id="location-id"
)
```

**Note**: `frame_id` is not configured. The framework automatically starts sync for each unique `frame_id` as robot poses are published.

**Note**: The ownership signature property is `syncOrigin`, with value set to `ConnectorConfig.connector_type`. The manager automatically injects this.

## Interfaces

### ExternalAnnotationProvider[TExternalPosition]

Protocol for external position providers:

```python
@runtime_checkable
class ExternalAnnotationProvider(Protocol[TExternalPosition]):
    async def list_positions(self, frame_id: str) -> list[TExternalPosition]: ...
    async def create_position(self, position: TExternalPosition) -> None: ...
    async def update_position(self, position_id: str, position: TExternalPosition) -> None: ...
    async def delete_position(self, position_id: str) -> None: ...
```

### AnnotationConverter[TExternalPosition]

Protocol for converting between positions and annotations:

```python
from inorbit_connector.inorbit import SpatialAnnotationData

@runtime_checkable
class AnnotationConverter(Protocol[TExternalPosition]):
    def position_to_annotation(
        self, position: TExternalPosition, frame_id: str
    ) -> SpatialAnnotationData: ...
    def annotation_to_position(
        self, annotation_data: SpatialAnnotationData
    ) -> TExternalPosition: ...
    def get_position_id(self, position: TExternalPosition) -> str: ...
```

**Note**: External positions must be Pydantic `BaseModel` subclasses.

## AnnotationSyncManager

Sync manager for synchronizing positions between external systems and InOrbit.

### Constructor

```python
from inorbit_connector.annotation_sync import AnnotationSyncManager
from inorbit_connector.inorbit import InOrbitConfigAPI

manager = AnnotationSyncManager(
    config=AnnotationSyncConfig(...),
    inorbit_config_client=InOrbitConfigAPI(...),
    position_provider=MyPositionProvider(),
    annotation_converter=MyAnnotationConverter(),
    account_id="account-id",
    frame_id="map",
    signature_value="connector-type"
)
```

**Note**: The framework creates manager instances automatically when new `frame_id`s are detected.

### Methods

- `start()` / `stop()`: Start/stop periodic synchronization
- `sync_once()`: Execute single sync based on configured mode
- `sync_external_to_inorbit()`: Sync from external system to InOrbit
- `sync_inorbit_to_external()`: Sync from InOrbit to external system

## Implementation Example

```python
from pydantic import BaseModel
from inorbit_connector.annotation_sync import (
    AnnotationSyncConfig,
    AnnotationSyncManager,
    ExternalAnnotationProvider,
    AnnotationConverter,
)
from inorbit_connector.inorbit import (
    SpatialAnnotationData,
    WaypointAnnotationSpec,
    WaypointData,
)

class MyPosition(BaseModel):
    id: str
    name: str
    x: float
    y: float
    theta: float

class MyProvider:
    async def list_positions(self, frame_id: str) -> list[MyPosition]: ...
    # ... other methods

class MyConverter:
    def position_to_annotation(
        self, position: MyPosition, frame_id: str
    ) -> SpatialAnnotationData:
        return SpatialAnnotationData(
            id=position.id,
            spec=WaypointAnnotationSpec(
                frameId=frame_id,
                label=position.name,
                data=WaypointData(x=position.x, y=position.y, theta=position.theta)
            )
        )
    # ... other methods

class MyConnector(FleetConnector):
    def __init__(self, config):
        super().__init__(config)
        self.register_annotation_sync(MyProvider(), MyConverter())
```

See the [Annotation Sync Usage Guide](../usage/annotation-sync) for more details.
