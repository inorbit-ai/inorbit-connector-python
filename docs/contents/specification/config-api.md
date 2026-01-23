---
title: "Config API"
description: "InOrbit Config API client and models"
---

The Config API provides access to InOrbit's configuration management system for managing configuration objects like spatial annotations.

For more information about the Config API, see the [InOrbit Developer Documentation](https://developer.inorbit.ai/docs#configuration-management).

## Models

### ConfigObject

Base model for all Config API objects:

```python
from inorbit_connector.inorbit import ConfigObject, ConfigObjectMetadata

class ConfigObject(BaseModel, Generic[TSpec]):
    apiVersion: Literal["v0.1"] = "v0.1"
    kind: str
    metadata: ConfigObjectMetadata
    spec: TSpec
```

### SpatialAnnotation

Model for spatial annotations (waypoints, zones, etc.):

```python
from inorbit_connector.inorbit import SpatialAnnotation, WaypointAnnotationSpec

annotation = SpatialAnnotation(
    metadata=ConfigObjectMetadata(
        id="waypoint-001",
        scope="tag/company-id/location-id"
    ),
    spec=WaypointAnnotationSpec(
        frameId="map",
        label="Dock Station",
        data=WaypointData(x=1.0, y=2.0, theta=0.0),
        properties={}
    )
)
```

## InOrbitConfigAPI

Client for interacting with the Config API.

### Constructor

```python
from inorbit_connector.inorbit import InOrbitConfigAPI

client = InOrbitConfigAPI(
    base_url="https://api.inorbit.ai",
    api_key="your-api-key",
    timeout=30
)
```

### Methods

#### `list_objects()`

```python
async def list_objects(
    kind: str,
    scope: str,
    format: str = "full"
) -> list[ConfigObject]
```

#### `apply_object()`

```python
async def apply_object(obj: ConfigObject) -> ConfigObject
```

#### `delete_object()`

```python
async def delete_object(obj: ConfigObject) -> None
```

#### `synchronize_objects()`

```python
async def synchronize_objects(
    scope: str,
    objects: list[ConfigObject],
    filter_fn: Optional[Callable[[ConfigObject], bool]] = None
) -> dict
```

Synchronizes objects with InOrbit by creating, updating, and deleting as needed. Deletion happens automatically for objects that no longer exist locally (filtered by `filter_fn` if provided).

Returns sync statistics: `created`, `updated`, `up_to_date`, `deleted`.

## Example

```python
from inorbit_connector.inorbit import (
    InOrbitConfigAPI,
    SpatialAnnotation,
    ConfigObjectMetadata,
    WaypointAnnotationSpec,
    WaypointData,
)

client = InOrbitConfigAPI(base_url=url, api_key=key)

# List annotations
annotations = await client.list_objects(
    kind="SpatialAnnotation",
    scope="tag/company/location"
)

# Create annotation
annotation = SpatialAnnotation(
    metadata=ConfigObjectMetadata(id="wp1", scope="tag/company/location"),
    spec=WaypointAnnotationSpec(
        frameId="map",
        label="Waypoint 1",
        data=WaypointData(x=1.0, y=2.0, theta=0.0)
    )
)
await client.apply_object(annotation)

# Delete annotation
await client.delete_object(annotation)
```
