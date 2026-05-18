---
title: "Metrics"
description: "Expose connector health metrics over Prometheus"
---

The framework ships an OpenTelemetry-based metrics subsystem that connectors can expose over a Prometheus HTTP endpoint. The defaults aim at a single use case: **knowing when something breaks**, suitable for alerting. Concrete connectors add their own domain metrics on top using the same OpenTelemetry primitives the [`inorbit-edge` SDK](https://github.com/inorbit-ai/edge-sdk-python) uses internally.

## What you get out of the box

When `metrics.enabled = true` in your connector configuration, the framework starts a Prometheus HTTP server and exposes:

Every framework metric is namespaced by `connector_type` at the source.
With `connector_type="acme"` (set on `ConnectorConfig`), the four
framework signals come out as:

| Metric | Type | Attributes | Meaning |
|---|---|---|---|
| `inorbit_acme_connector_up` | Gauge | — | 1 while the connector's main thread is alive |
| `inorbit_acme_connector_session_connected` | Gauge | `robot_id` | 1 when the per-robot MQTT session to InOrbit is connected. Catches the "process running but robot offline" failure mode where MQTT drops and reconnect fails |
| `inorbit_acme_connector_execution_loop_ticks_total` | Counter | — | Successful iterations of `_execution_loop` |
| `inorbit_acme_connector_execution_loop_errors_total` | Counter | — | Exceptions caught in the run loop |

Plus the per-robot publish counters that come from the SDK (same
namespacing):

| Metric | Attributes | Meaning |
|---|---|---|
| `inorbit_acme_connector_calls_publish_pose_total` | `robot_id` | Calls to `publish_pose` |
| `inorbit_acme_connector_calls_publish_odometry_total` | `robot_id` | Calls to `publish_odometry` |
| `inorbit_acme_connector_calls_publish_key_values_total` | `robot_id` | Calls to `publish_key_values` |
| `inorbit_acme_connector_calls_publish_system_stats_total` | `robot_id` | Calls to `publish_system_stats` |
| `inorbit_acme_connector_calls_publish_map_total` | `robot_id` | Calls to `publish_map` |
| `inorbit_acme_connector_calls_publish_camera_frame_total` | `robot_id` | Calls to `publish_camera_frame` |
| `inorbit_acme_connector_calls_publish_lasers_total` | `robot_id` | Calls to `publish_lasers` / `publish_laser` |
| `inorbit_acme_connector_calls_publish_path_total` | `robot_id` | Calls to `publish_path` |

The per-connector-type prefix means descriptors in any downstream metric
store are isolated by connector type — two connectors built on this
framework never collide. To query across connector types, use a wildcard
(`inorbit_*_connector_*`) and rely on the `connector_type` label
attached automatically.

These signals are usually enough for an MVP alerting setup:

```promql
# Process is dead or scrape failing — across every connector type
inorbit_.*_connector_up == 0

# Process is up but its MQTT link to InOrbit is down (robot appears offline)
inorbit_.*_connector_session_connected == 0

# Process is up but not progressing
rate(inorbit_acme_connector_execution_loop_ticks_total[5m]) == 0

# Process is up but erroring
rate(inorbit_acme_connector_execution_loop_errors_total[5m]) > 0
```

## Enabling metrics

Add a `metrics:` block to your connector configuration:

```yaml
metrics:
  enabled: true
  bind_host: 127.0.0.1   # bind interface; use 0.0.0.0 for bridge networking
  bind_port: 9090        # 0 picks an ephemeral free port
  connector_id: my-bot   # unique per process on a host
  discovery_dir: /var/run/inorbit-metrics  # for OTEL collector file_sd
```

When enabled, the connector also writes a Prometheus `file_sd`-format JSON file to `discovery_dir`, naming the bound `host:port`. A host-side OTEL collector can mount this directory and discover every connector running on the host — see [`examples/metrics/`](https://github.com/inorbit-ai/inorbit-connector-python/tree/main/examples/metrics) for a reference compose stack.

If your scraper is configured statically (e.g. its `prometheus.yaml` already lists `host:port` targets, or you only run a single connector behind a known address), set `discovery_dir: null` to skip writing the discovery file entirely. The HTTP endpoint still serves `/metrics` as usual.

When `enabled` is `false` (the default), no server is started and all instruments become no-ops with zero overhead.

### Configuration reference

| Field | Default | Notes |
|---|---|---|
| `enabled` | `false` | Master switch. When false, the rest of the block is ignored. |
| `bind_host` | `0.0.0.0` | Address the HTTP server binds to. |
| `bind_port` | `9090` | TCP port. Use `0` to let the OS pick. |
| `advertise_host` | `socket.gethostname()` | Hostname written to the discovery file. |
| `discovery_dir` | `/var/run/inorbit-metrics` | Auto-created on start. Set to `null` to skip writing a discovery file. |
| `connector_id` | `socket.gethostname()` | Used as `service.instance.id` and as the discovery filename. |
| `exporter_namespace` | `None` (auto: `inorbit_<connector_type>_connector`) | Prefix prepended to every Prometheus metric name. ASCII / no hyphens. Set explicitly only to override the auto-derived value. |
| `extra_resource_attributes` | `{}` | Added to every metric as OTEL Resource attributes (low-cardinality only). |

## Adding metrics to your connector

For domain metrics, use the SDK helpers directly. The connector framework imposes no wrapper.

### Step 1 — Declare a meter and instruments

```python
# my_connector/metrics.py
from inorbit_edge.metrics import get_meter

meter = get_meter("inorbit_my_connector")

api_requests = meter.create_counter(
    "api.requests", unit="1", description="Calls to the device API",
)
api_errors = meter.create_counter(
    "api.errors", unit="1", description="Failed calls to the device API",
)
```

The same module-level pattern the SDK uses for its own counters. `get_meter` returns a real OTEL `Meter` when telemetry deps are installed (always the case via `inorbit-edge[telemetry]`), or a no-op `Meter` otherwise.

#### Naming rule: don't repeat the namespace in instrument names

`exporter_namespace` is prepended to every metric on export — for a connector with `connector_type="acme"`, the framework derives `inorbit_acme_connector`, so `api.requests` above surfaces as `inorbit_acme_connector_api_requests_total` on `/metrics`. Don't add the namespace to the instrument name yourself — the meter name is decorative (it surfaces only as `instrumentation_scope`); the instrument name is the metric.

- ✅ `meter.create_counter("api.requests", ...)` → `inorbit_acme_connector_api_requests_total`
- ❌ `meter.create_counter("inorbit.acme.connector.api.requests", ...)` → `inorbit_acme_connector_inorbit_acme_connector_api_requests_total`

A double-prefixed wire name can only be cleaned up by a collector-side `metric_relabel_configs` rule that rewrites `__name__`. Those rewrites strip the Prometheus `# TYPE` line, so the metric arrives at the OTEL pipeline as `UNKNOWN` and is exported as a Gauge regardless of its real type. Downstream metric stores that pin descriptor kind on first write (GCP Cloud Monitoring, for example) then silently drop later writes of the correct type.

### Step 2 — Instrument calls

Two patterns; pick whichever fits the call site:

**Decorator (counts every call to a method)**

```python
from inorbit_edge.metrics import with_counter_metric

class DeviceAPI:
    @with_counter_metric(api_requests, attributes={"endpoint": "/status"})
    async def get_status(self):
        ...
```

`with_counter_metric` works on sync and async methods. The `attributes` argument may be a static dict or a callable that returns one. For attributes that come from the bound instance, use `attrs_from_self`:

```python
from inorbit_edge.metrics import with_counter_metric, attrs_from_self

class DeviceAPI:
    def __init__(self, robot_id):
        self.robot_id = robot_id

    @with_counter_metric(api_requests, attributes=attrs_from_self("robot_id"))
    async def get_status(self):
        ...
```

**Inline (anywhere — error paths, observable state, custom events)**

```python
async def get_status(self):
    try:
        return await self._client.get("/status")
    except Exception:
        api_errors.add(1, {"endpoint": "/status"})
        raise
```

## When to use which scope

The single decision that drives metric design is: **how many upstream entities does one connector process talk to?**

- **N=1** (single-robot connector, single-PLC connector, etc.): `service.instance.id` already identifies the process. Don't add a `robot_id` / `device_id` attribute on per-call metrics — it would duplicate the Resource attribute that the OTEL collector already attaches.
- **N>1** (`FleetConnector` for a fleet manager API, gateway controlling many doors, etc.): add the entity id as a per-call attribute. Use `attrs_from_self("robot_id")` for instance-bound calls; pass it explicitly to `.add()` / `.record()` for ad-hoc sites.

For non-robot connectors, name the attribute after the domain entity: `device_id`, `plc_id`, `door_id`, `elevator_id`. Same pattern, different label name.

## Cardinality guardrails

OTEL attributes become Prometheus labels. Each unique label-value combination is a separate time series, and series count is the dominant cost driver for both Prometheus and managed services like GCP Cloud Monitoring. Use bounded enums; never put unbounded values in attributes.

| Attribute | Examples (good) | Examples (bad) |
|---|---|---|
| `endpoint` | `/status`, `/missions` | `/missions/<uuid>` |
| `result` | `success`, `error` | exception messages |
| `status` | `200`, `404`, `500` (or `2xx`/`4xx`/`5xx`) | full status text |
| `topic_pattern` | `robot/cmd/velocity` | `robot/<id>/cmd/velocity` |

Forbidden in attributes: full URLs containing IDs, exception messages, query strings, free-form user input.

If you need to mask out an ID-like segment from a value before recording, do it in the connector before the `.add()` call.

## Observable instruments

For state derived from connector internals (battery level, broker connected, queue depth), prefer `create_observable_gauge` with a callback that reads state at scrape time:

```python
from inorbit_edge.metrics import Observation, get_meter

meter = get_meter("inorbit_my_connector")

class DeviceClient:
    def __init__(self):
        self._connected = False

        meter.create_observable_gauge(
            "my.broker.connected",
            callbacks=[self._connected_cb],
            unit="1",
            description="1 when the connector is connected to the broker",
        )

    def _connected_cb(self, _options):
        return [Observation(1 if self._connected else 0)]
```

The callback runs on every scrape, so it should be cheap and side-effect free.

## Production deployment

For multi-container deployments, see [`examples/metrics/`](https://github.com/inorbit-ai/inorbit-connector-python/tree/main/examples/metrics) for a reference OTEL collector compose stack that:

- Discovers all connector containers on a host via Prometheus `file_sd`.
- Exports to GCP Cloud Monitoring (other backends straightforward to swap in).
- Works with both bridge and host Docker networking modes.
