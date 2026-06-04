---
title: "Metrics"
description: "Expose connector health metrics over Prometheus"
---

The framework ships an OpenTelemetry-based metrics subsystem that connectors can expose over a Prometheus HTTP endpoint. The defaults aim at a single use case: **knowing when something breaks**, suitable for alerting. Concrete connectors add their own domain metrics on top using the same OpenTelemetry primitives the [`inorbit-edge` SDK](https://github.com/inorbit-ai/edge-sdk-python) uses internally.

## What you get out of the box

When `metrics.enabled = true` in your connector configuration, the framework starts a Prometheus HTTP server and exposes:

Every framework metric uses the constant `inorbit_connector` wire prefix.
The connector type is NOT part of the metric name — it rides on every
series as the `inorbit_connector_type` Prometheus label (sourced from the
`inorbit.connector.type` OpenTelemetry Resource attribute). One descriptor
per metric covers every connector type; cross-type aggregation works
without metric-name fan-out.

| Metric | Type | Attributes | Meaning |
|---|---|---|---|
| `inorbit_connector_up` | Gauge | — | 1 while the connector's main thread is alive |
| `inorbit_connector_session_connected` | Gauge | `robot_id` | 1 when the per-robot MQTT session to InOrbit is connected. Catches the "process running but robot offline" failure mode where MQTT drops and reconnect fails |
| `inorbit_connector_execution_loop_ticks_total` | Counter | — | Successful iterations of `_execution_loop` |
| `inorbit_connector_execution_loop_errors_total` | Counter | — | Exceptions caught in the run loop |

Plus the canonical upstream-HTTP family (recorded whenever you call the
helpers in `inorbit_connector.metrics.http`) and the per-robot publish
counters that come from the SDK:

| Metric | Attributes | Meaning |
|---|---|---|
| `inorbit_connector_upstream_http_requests_total` | `vendor`, `method`, `endpoint` | Successful upstream HTTP calls |
| `inorbit_connector_upstream_http_errors_total` | `vendor`, `method`, `endpoint`, `error_kind` | Failed upstream HTTP calls |
| `inorbit_connector_upstream_http_duration_seconds_*` | `vendor`, `method`, `endpoint` | Latency histogram of upstream calls (both paths) |
| `calls_publish_pose_total` | `robot_id` | Calls to `publish_pose` |
| `calls_publish_odometry_total` | `robot_id` | Calls to `publish_odometry` |
| `calls_publish_key_values_total` | `robot_id` | Calls to `publish_key_values` |
| `calls_publish_system_stats_total` | `robot_id` | Calls to `publish_system_stats` |
| `calls_publish_map_total` | `robot_id` | Calls to `publish_map` |
| `calls_publish_camera_frame_total` | `robot_id` | Calls to `publish_camera_frame` |
| `calls_publish_lasers_total` | `robot_id` | Calls to `publish_lasers` / `publish_laser` |
| `calls_publish_path_total` | `robot_id` | Calls to `publish_path` |

Every series also carries the `inorbit_connector_id` label (one value per process, sourced from `service.instance.id`), so two connectors on the same host never collide on `(metric, labels)` even though they share the wire prefix.

These signals are usually enough for an MVP alerting setup:

```promql
# Process is dead or scrape failing — covers every connector type
inorbit_connector_up == 0

# Process is up but its MQTT link to InOrbit is down (robot appears offline)
inorbit_connector_session_connected == 0

# Process is up but not progressing — slice by connector type if needed
rate(inorbit_connector_execution_loop_ticks_total[5m]) == 0

# Process is up but erroring
rate(inorbit_connector_execution_loop_errors_total[5m]) > 0

# Same query, scoped to one connector type
rate(inorbit_connector_execution_loop_errors_total{inorbit_connector_type="acme"}[5m]) > 0
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
| `extra_resource_attributes` | `{}` | Added to every metric as OTEL Resource attributes (low-cardinality only). |

The wire-level metric prefix is always `inorbit_connector`. The connector type rides on every metric as the `inorbit.connector.type` Resource attribute (a Prometheus label), not as part of the metric name — cross-connector aggregation works on a single descriptor per metric.

## Adding metrics to your connector

This section covers **domain metrics** — counters and histograms for vendor-specific business state (mission outcomes, command results, queue depths, device state transitions). For outbound HTTP calls to your upstream API, use the canonical helpers instead: `record_upstream_http_request()` / `record_upstream_http_error()` from `inorbit_connector.metrics.http`. They own the request/error/duration descriptors and the endpoint-cardinality normalizers (`EndpointMapper`, `PathTemplater`) — don't reimplement them as domain counters.

### Step 1 — Declare a meter and instruments

```python
# my_connector/metrics.py
from inorbit_connector.metrics import get_connector_meter

meter = get_connector_meter("acme")   # match your connector_type

mission_failures = meter.create_counter(
    "mission.failures",
    unit="1",
    description="Missions that ended in failure (attribute: reason)",
)
command_executions = meter.create_counter(
    "command.executions",
    unit="1",
    description="Vendor commands executed (attribute: command_name, result)",
)
```

Module-level declaration, same pattern the SDK uses for its own counters. `get_connector_meter` wraps an OTEL `Meter` so every instrument name is automatically prefixed with `<connector_type>.` — `mission.failures` above is created on the underlying meter as `acme.mission.failures` and exports on the wire as `inorbit_connector_acme_mission_failures_total`.

#### Naming rule: don't repeat the connector type in instrument names

The wrapper adds the prefix structurally; doing it again duplicates it on the wire.

- ✅ `meter.create_counter("mission.failures", ...)` → `inorbit_connector_acme_mission_failures_total`
- ❌ `meter.create_counter("acme.mission.failures", ...)` → `inorbit_connector_acme_acme_mission_failures_total`

A double-prefixed wire name can only be cleaned up by a collector-side `metric_relabel_configs` rule that rewrites `__name__`. Those rewrites strip the Prometheus `# TYPE` line, so the metric arrives at the OTEL pipeline as `UNKNOWN` and is exported as a Gauge regardless of its real type. Downstream metric stores that pin descriptor kind on first write (GCP Cloud Monitoring, for example) then silently drop later writes of the correct type.

### Step 2 — Instrument call sites

Two patterns; pick whichever fits the site:

**Inline (the common case — record on the path that actually produces the event)**

```python
async def _handle_mission(self, mission):
    try:
        await self._executor.run(mission)
    except MissionError as exc:
        mission_failures.add(1, {"reason": exc.category})
        raise
```

`reason` is a bounded enum — drawn from a known set (`timeout`, `aborted`, `precondition_failed`, ...). Don't pass the raw exception message; it explodes the descriptor's label space.

**Decorator (counts every call to a method, regardless of outcome)**

```python
from inorbit_edge.metrics import with_counter_metric, attrs_from_self

class MissionExecutor:
    def __init__(self, robot_id):
        self.robot_id = robot_id

    @with_counter_metric(command_executions, attributes=attrs_from_self("robot_id"))
    async def run(self, command):
        ...
```

`with_counter_metric` works on sync and async methods. `attributes` may be a static dict or a callable that returns one. Use `attrs_from_self("robot_id")` to forward instance attributes onto each recorded sample.

## When to use which scope

The single decision that drives metric design is: **how many upstream entities does one connector process talk to?**

- **N=1** (single-robot connector, single-PLC connector, etc.): `service.instance.id` already identifies the process. Don't add a `robot_id` / `device_id` attribute on per-call metrics — it would duplicate the Resource attribute that the OTEL collector already attaches.
- **N>1** (`FleetConnector` for a fleet manager API, gateway controlling many doors, etc.): add the entity id as a per-call attribute. Use `attrs_from_self("robot_id")` for instance-bound calls; pass it explicitly to `.add()` / `.record()` for ad-hoc sites.

For non-robot connectors, name the attribute after the domain entity: `device_id`, `plc_id`, `door_id`, `elevator_id`. Same pattern, different label name.

## Cardinality guardrails

OTEL attributes become Prometheus labels. Each unique label-value combination is a separate time series, and series count is the dominant cost driver for both Prometheus and managed services like GCP Cloud Monitoring. Use bounded enums; never put unbounded values in attributes.

| Attribute | Examples (good) | Examples (bad) |
|---|---|---|
| `reason` | `timeout`, `aborted`, `precondition_failed` | exception messages |
| `result` | `success`, `failure`, `cancelled` | free-form server-returned phrase |
| `command_name` | `pause_robot`, `resume_robot` | dynamic command strings from upstream |
| `topic_pattern` | `robot/cmd/velocity` | `robot/<id>/cmd/velocity` |

Forbidden in attributes: full URLs containing IDs, exception messages, query strings, free-form user input, anything sourced from the upstream API without classification.

If you need to mask out an ID-like segment from a value before recording, do it in the connector before the `.add()` call. For HTTP endpoint labels, use `EndpointMapper` / `PathTemplater` from `inorbit_connector.metrics.http`.

## Observable instruments

For state derived from connector internals (battery level, broker connected, queue depth), prefer `create_observable_gauge` with a callback that reads state at scrape time:

```python
from inorbit_edge.metrics import Observation
from inorbit_connector.metrics import get_connector_meter

meter = get_connector_meter("acme")

class DeviceClient:
    def __init__(self):
        self._connected = False

        meter.create_observable_gauge(
            "broker.connected",
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
