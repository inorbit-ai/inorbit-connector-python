---
title: "Annotation Synchronization"
description: "API specification for synchronizing annotations between external systems and InOrbit"
---

# Annotation Synchronization API

The annotation synchronization framework enables connectors to synchronize annotations (currently waypoints) between external systems and InOrbit's Config API.

## Terminology

- **Annotation**: An InOrbit `SpatialAnnotation` object (kind: `SpatialAnnotation`). Currently, we support waypoint annotations (`spec.type == "waypoint"`).
- **Position**: A relevant position in the external system. This is the external system's representation that maps to a waypoint annotation in InOrbit.
- **External system**: The software the connector interacts with, such as a fleet manager (MiR Fleet, Bluebotics) or native robot software.

## Overview

The framework provides:

- **InOrbitConfigClient**: Client for InOrbit's Config API
- **AnnotationSyncManager**: Sync manager with logic for sync modes
- **Interfaces**: `ExternalAnnotationProvider` and `AnnotationConverter` for connector implementations
- **Models**: Configuration and data models (`AnnotationSyncConfig`, `SpatialAnnotation`)

The framework instantiates `InOrbitConfigClient` using `ConnectorConfig.rest_api_url`
(environment variable `INORBIT_REST_API_URL`). This REST API base URL is distinct
from the robot session endpoint configured in `ConnectorConfig.api_url`.

## Module Structure

All annotation sync components are under `inorbit_connector/waypoint_sync/`:

```
inorbit_connector/
└── waypoint_sync/
    ├── __init__.py         # Exports main classes
    ├── config_client.py    # InOrbit Config API client
    ├── interfaces.py       # Provider and converter protocols
    ├── models.py           # Configuration and data models
    └── manager.py          # Sync manager
```

---

## Config API Models {#spec-annotation-sync-config-api-models}

All Config API objects share a common structure:

```python
class ConfigObjectMetadata(BaseModel):
    """Metadata for Config API objects."""
    id: str
    scope: Optional[str] = None

class ConfigObject(BaseModel):
    """Base model for InOrbit Config API objects."""
    apiVersion: Literal["v0.1"] = "v0.1"
    kind: str
    metadata: ConfigObjectMetadata
```

## SpatialAnnotation Models {#spec-annotation-sync-spatial-annotation}

Pydantic models representing InOrbit's SpatialAnnotation objects.

```python
class WaypointData(BaseModel):
    """Pose data for waypoint annotations."""
    x: float
    y: float
    theta: float

class WaypointAnnotationSpec(BaseModel):
    """Specification for waypoint spatial annotations."""
    type: Literal["waypoint"] = "waypoint"
    frameId: str
    label: str
    properties: dict = {}
    data: WaypointData

class SpatialAnnotationData(BaseModel):
    """Minimal annotation data for converter interface."""
    id: str
    spec: WaypointAnnotationSpec

class SpatialAnnotation(ConfigObject):
    """InOrbit SpatialAnnotation model."""
    kind: Literal["SpatialAnnotation"] = "SpatialAnnotation"
    metadata: ConfigObjectMetadata
    spec: WaypointAnnotationSpec
```

**Note**: Converters work with `SpatialAnnotationData` (id + spec only). The manager
constructs full `SpatialAnnotation` objects with metadata, apiVersion, kind, and
ownership signatures.

Use Pydantic's built-in methods for serialization:
- `model_dump()` / `model_dump(mode="json")`: Convert to dictionary
- `model_validate(data)`: Create from dictionary

---

## InOrbitConfigClient {#spec-annotation-sync-config-client}

Client for InOrbit's Configuration API.

### Constructor

```python
InOrbitConfigClient(
    base_url: str,
    api_key: str,
    timeout: int = 30
)
```

### Methods

#### `list_annotations()` {#spec-annotation-sync-list-annotations}

Retrieve spatial annotations from InOrbit.

```python
async def list_annotations(
    scope: str,
    format: str = "full"
) -> list[SpatialAnnotation]
```

#### `apply_annotation()` {#spec-annotation-sync-apply-annotation}

Create or update an annotation.

```python
async def apply_annotation(
    annotation: SpatialAnnotation
) -> SpatialAnnotation
```

#### `synchronize_annotations()` {#spec-annotation-sync-synchronize-annotations}

Synchronize annotations with InOrbit.

```python
async def synchronize_annotations(
    scope: str,
    annotations: list[SpatialAnnotation],
    filter_fn: Optional[Callable[[SpatialAnnotation], bool]] = None
) -> dict
```

**Returns**: Sync statistics with `created`, `updated`, `up_to_date`, `to_delete`, `to_delete_count`.

---

## AnnotationSyncConfig {#spec-annotation-sync-config}

Configuration model for annotation synchronization.

Scopes use `ConnectorConfig.account_id` together with `AnnotationSyncConfig.location_id`.

**Note**: `frame_id` is not configured here. The framework automatically starts sync
for each unique frame_id as robot poses are published, supporting fleet connectors
where robots operate on multiple maps.

**Note**: The ownership signature property name is fixed to `syncOrigin`, and the
signature value is the connector type (`ConnectorConfig.connector_type`). The manager
automatically injects this signature into annotations.

```python
class AnnotationSyncConfig(BaseModel):
    enabled: bool = False
    mode: AnnotationSyncMode = AnnotationSyncMode.EXTERNAL_TO_INORBIT
    sync_interval_seconds: int = 300
    location_id: Optional[str] = None
```

### AnnotationSyncMode {#spec-annotation-sync-mode}

```python
class AnnotationSyncMode(str, Enum):
    EXTERNAL_TO_INORBIT = "external_to_inorbit"  # External → InOrbit
    INORBIT_TO_EXTERNAL = "inorbit_to_external"  # InOrbit → External
```

---

## Interfaces {#spec-annotation-sync-interfaces}

The framework uses a generic type `TExternalPosition` for external positions:

```python
TExternalPosition = TypeVar("TExternalPosition", bound=BaseModel)
```

External positions **must** be Pydantic `BaseModel` subclasses. This enables:
- Consistent serialization via `model_dump()`
- Type-safe comparisons in update detection
- Validation on construction

### ExternalAnnotationProvider[TExternalPosition] {#spec-annotation-sync-external-provider}

Protocol for external position providers. Connectors implement this to provide CRUD access to positions in their external system.

```python
@runtime_checkable
class ExternalAnnotationProvider(Protocol[TExternalPosition]):
    async def list_positions(self, frame_id: str) -> list[TExternalPosition]:
        """Fetch positions from the external system for a specific frame.

        Implementations should filter positions to only return those
        that belong to the specified frame_id (map).
        """
        ...

    async def create_position(self, position: TExternalPosition) -> None:
        """Create a new position."""
        ...

    async def update_position(
        self, position_id: str, position: TExternalPosition
    ) -> None:
        """Update existing position."""
        ...

    async def delete_position(self, position_id: str) -> None:
        """Delete a position."""
        ...
```

### AnnotationConverter[TExternalPosition] {#spec-annotation-sync-converter}

Protocol for converting between positions and annotation data.

```python
@runtime_checkable
class AnnotationConverter(Protocol[TExternalPosition]):
    def position_to_annotation(
        self, position: TExternalPosition, frame_id: str
    ) -> SpatialAnnotationData:
        """Convert external position to SpatialAnnotationData.

        Args:
            position: The external position to convert
            frame_id: The frame/map ID for this annotation
        """
        ...

    def annotation_to_position(
        self, annotation_data: SpatialAnnotationData
    ) -> TExternalPosition:
        """Convert SpatialAnnotationData to external position."""
        ...

    def get_position_id(self, position: TExternalPosition) -> str:
        """Extract unique ID from position."""
        ...
```

---

## AnnotationSyncManager[TExternalPosition] {#spec-annotation-sync-manager}

Annotation synchronization manager. One manager instance is created per unique `frame_id`.

### Constructor

```python
AnnotationSyncManager(
    config: AnnotationSyncConfig,
    inorbit_config_client: InOrbitConfigClient,
    position_provider: ExternalAnnotationProvider[TExternalPosition],
    annotation_converter: AnnotationConverter[TExternalPosition],
    account_id: Optional[str],
    frame_id: str,  # The frame/map ID this manager syncs for
    signature_value: str,  # Connector type used for ownership signature
)
```

**Note**: The framework creates manager instances automatically when new frame_ids
are detected during `publish_robot_pose()` calls.

### Methods

#### `start()` / `stop()` {#spec-annotation-sync-lifecycle}

```python
def start(self) -> None:
    """Start periodic annotation synchronization."""

async def stop(self) -> None:
    """Stop periodic annotation synchronization."""
```

#### `sync_once()` {#spec-annotation-sync-sync-once}

```python
async def sync_once(self) -> dict:
    """Execute single sync based on configured mode."""
```

#### `sync_external_to_inorbit()` {#spec-annotation-sync-external-to-inorbit}

```python
async def sync_external_to_inorbit(self) -> dict
```

Sync positions from external system to InOrbit annotations.

#### `sync_inorbit_to_external()` {#spec-annotation-sync-inorbit-to-external}

```python
async def sync_inorbit_to_external(self) -> dict
```

Sync annotations from InOrbit to external system positions.

---

## Implementing Annotation Sync in a Connector

### 1. Define Position Model (Pydantic BaseModel)

External positions **must** be Pydantic `BaseModel` subclasses:

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

```python
class MyPositionProvider:
    async def list_positions(self, frame_id: str) -> list[MyPosition]:
        # Filter positions to only those on the specified map
        data = await self._client.get_positions(map_id=frame_id)
        return [MyPosition.model_validate(p) for p in data]

    async def create_position(self, position: MyPosition) -> None:
        await self._client.create(position.model_dump())
    # ... implement other methods
```

### 3. Implement AnnotationConverter

```python
from inorbit_connector.waypoint_sync.models import (
    SpatialAnnotationData,
    WaypointAnnotationSpec,
    WaypointData,
)

class MyAnnotationConverter:
    def position_to_annotation(
        self, position: MyPosition, frame_id: str
    ) -> SpatialAnnotationData:
        """Convert position to SpatialAnnotationData using provided frame_id."""
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
        return MyPosition(
            id=annotation_data.id,
            name=annotation_data.spec.label,
            x=annotation_data.spec.data.x,
            y=annotation_data.spec.data.y,
            orientation=annotation_data.spec.data.theta
        )

    def get_position_id(self, position: MyPosition) -> str:
        return position.id
```

### 4. Register Implementations with the Framework

```python
class MyConnector(FleetConnector):
    def __init__(self, config):
        super().__init__(config)

        # Create provider and converter (frame_id is handled dynamically)
        provider = MyPositionProvider(my_client)
        converter = MyAnnotationConverter()

        # Register with framework
        self.register_annotation_sync(provider, converter)
```

The framework will:
1. Initialize the Config API client during `connect()`
2. Create `AnnotationSyncManager` instances per unique `frame_id` when poses are published
3. Pass the `frame_id` to `list_positions()` and `position_to_annotation()`
4. Manage start/stop of all managers automatically
5. Inject ownership signatures automatically

See the [Annotation Sync Usage Guide](../usage/annotation-sync) for more details.
