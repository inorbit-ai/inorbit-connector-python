<!--
SPDX-FileCopyrightText: 2026 InOrbit, Inc.
SPDX-License-Identifier: MIT
-->

# Reference: metrics export with an OTel collector

This directory holds a reference setup for collecting metrics from one or more
`inorbit-connector` containers on a single host and forwarding them to GCP
Cloud Monitoring via the **`googlemanagedprometheus` exporter**, which writes
them as the Prometheus descriptor type (`prometheus.googleapis.com/...`).
Compared to the Custom type that the plain `googlecloud` exporter produces,
the Prometheus type lifts the per-descriptor caps to **200 labels** and
**25K descriptors per project** (versus 30 / 10K), raises the active-series
cap per descriptor to 1M (versus 200K), and makes every metric queryable
with **PromQL** in the Cloud Monitoring console and Grafana. Descriptor
exhaustion on the Custom type is the practical ceiling on fleet growth
across connector types, which is why the `custom.googleapis.com/` /
`workload.googleapis.com/` route is not used here.

It is intentionally an **example**, not a turn-key deployment: ports,
hostnames, exporters, and credential mounts will all need to be adjusted for
your environment. For the supported `metrics:` configuration fields, see the
[Metrics user guide](../../docs/contents/usage/metrics.md).

## Design rules

The example config in this directory encodes two rules that keep metrics
flowing into a managed metric backend (GCP Cloud Monitoring in
particular). Each addresses a failure mode that produces sparse data
with no clear error in the collector log.

> **Note on descriptor isolation.** A separate "one `metric.prefix` per
> connector type" rule used to live here. The framework now emits every
> metric under a single constant wire prefix (`inorbit_connector_*`) and
> rides the connector type on every series as the
> `inorbit_connector_type` Prometheus label (sourced from the
> `inorbit.connector.type` Resource attribute). Cross-vendor queries
> work without inspecting metric names — a single descriptor per metric
> covers every connector. Per-process isolation is provided by the
> `inorbit_connector_id` label (from `service.instance.id`).

### Rule 1 — Don't rewrite `__name__` in `metric_relabel_configs`

The Prometheus receiver warns at startup that any rule writing
`__name__` produces "unknown-typed metrics without a unit or
description". The renamed metric loses its Counter/Histogram type and
exports as a Gauge regardless of its real type — and that then pins the
downstream descriptor kind to `GAUGE`, which later writes of the
correct kind cannot recover from.

Fix metric names at the source (see [Metrics user
guide](../../docs/contents/usage/metrics.md)). Drop-only relabel rules
(no `target_label: __name__`) are safe — they filter before any naming
step.

### Rule 2 — Preserve per-series write ordering

GCP rejects `CUMULATIVE` and `DELTA` writes whose `interval.start_time`
precedes the last accepted `end_time` for the same series. Dropped
points produce no error log entry, only gaps on the chart. This
pipeline keeps cumulative counters as CUMULATIVE end to end and relies
on three invariants to keep writes monotonic:

- **One writer per series.** A series is keyed by metric name + labels.
  Every framework-emitted metric carries the connector's
  `service.instance.id` (=`inorbit.connector.id`) Resource attribute,
  which is unique per process, so two connectors never co-write the same
  series even though they share the constant `inorbit_connector_*` wire
  prefix. Don't add custom Resource attributes that would let two
  connector processes overlap on (metric, labels).
- **Serial sends.** `sending_queue.num_consumers: 1` makes the
  exporter's queue strictly FIFO. A retry blocks the queue rather
  than racing the next batch.
- **Single collector per fleet.** Two collector replicas scraping the
  same connector and writing to the same project would race; deploy
  one collector instance per metric-namespace scope.

CUMULATIVE has a self-healing property under transient failures: if a
batch is dropped permanently (queue eviction during a long outage,
exhausted retries), the next successful write still carries the full
running total, so the series's reconstruction stays correct from that
point on.

Connector restarts are handled natively. The Prometheus receiver
detects the counter reset (value decrease), advances the series's
`start_time`, and GCP recognizes it as a new cumulative epoch.
`ALIGN_RATE` charts and `rate(...)`-based alerts cross the restart
boundary without artifacts.

### Switching to a different metric backend

If you swap `googlemanagedprometheus` for Cortex/Mimir/Prometheus
remote_write, `num_consumers: 1` can be relaxed — those backends accept
out-of-order writes for cumulative counters and reconcile on the server
side. Rule 1 still applies to any backend that consumes Prometheus type
information.

## How it works

1. Each connector container runs a Prometheus-format HTTP endpoint bound to a
   configurable port (default `9090`). Under Docker bridge networking each
   container lives in its own network namespace, so a fixed port has no
   conflict.
2. Each connector writes a small JSON file to a shared Docker named volume
   (`inorbit-connector-metrics`). The file uses Prometheus `file_sd` format
   and names the connector's advertised address (for example `brand-1:9090`).
3. One OTel collector runs alongside the connectors, mounts the same volume
   read-only, and uses `file_sd_configs` to discover every connector. It
   scrapes them and exports to GCP via the `googlemanagedprometheus`
   exporter.

## One-shot host setup

```bash
docker volume create inorbit-connector-metrics
docker network create inorbit-metrics
```

## Connector-side configuration

Add a `metrics:` block to your connector's YAML configuration:

```yaml
metrics:
  enabled: true
  bind_host: 0.0.0.0           # bridge-network mode; use 127.0.0.1 for host networking
  bind_port: 9090
  advertise_host: brand-1        # must match the docker-compose `hostname:` field
  connector_id: brand-1          # unique per host; used as discovery filename
  discovery_dir: /var/run/inorbit-metrics
```

Mount the shared volume and join the shared network in the connector's
compose service:

```yaml
services:
  brand-1:
    image: inorbit/mir-connector:latest
    hostname: brand-1
    networks: [inorbit-metrics]
    volumes:
      - inorbit-connector-metrics:/var/run/inorbit-metrics
```

`connector_id` must be unique across all connector containers on the same
host — typically `<connector_type>-<robot_id>` or the docker-compose service
name.

For the connector configuration reference and metric catalog, see the
[Metrics user guide](../../docs/contents/usage/metrics.md).

## Collector-side setup

1. Place `otel-collector-compose.yaml` and `otel-collector-config.yaml` from
   this directory in a working directory on the host.
2. Put a GCP service-account key with `roles/monitoring.metricWriter` at
   `./gcp-sa.json`.
3. Export your GCP project:
   ```bash
   export GCP_PROJECT=your-project-id
   ```
4. Bring up the collector:
   ```bash
   docker compose -f otel-collector-compose.yaml up -d
   ```

## Verifying end-to-end

- On the host, list the discovery files:
  ```bash
  docker run --rm -v inorbit-connector-metrics:/v alpine ls /v
  ```
  Expected: one `<connector_id>.json` per running connector.

- Tail the collector logs:
  ```bash
  docker compose -f otel-collector-compose.yaml logs -f otel-collector
  ```
  Look for `Scrape iteration` entries referring to your connector targets.

- In GCP Cloud Monitoring, under **Prometheus** metrics, look for
  `prometheus.googleapis.com/inorbit_connector_*` series. Descriptor
  names carry a type suffix added by the exporter
  (`.../inorbit_connector_up/gauge`,
  `.../inorbit_connector_execution_loop_ticks_total/counter`); in PromQL
  you query by the bare wire name (`inorbit_connector_up`). Slice by the
  `connector_type` label to drill into one vendor. Or check from a
  terminal:

  ```bash
  PROJECT=$(gcloud config get-value project)
  curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    --get "https://monitoring.googleapis.com/v3/projects/${PROJECT}/metricDescriptors" \
    --data-urlencode 'filter=metric.type = starts_with("prometheus.googleapis.com/inorbit_connector")' \
    | jq -r '.metricDescriptors[].type'
  ```

## Host-networking alternative

If `network_mode: host` is acceptable, set `metrics.bind_host: 127.0.0.1`
and `metrics.bind_port: 0` (ephemeral) on each connector. The discovery
files then contain entries like `127.0.0.1:41273`. The collector service
must also use `network_mode: host` to share the loopback interface; drop
its `networks:` stanza and add `network_mode: host`.

## Security considerations

- `/metrics` endpoints are unauthenticated on the internal Docker network.
  Treat the `inorbit-metrics` network as trusted.
- In host-networking mode, connectors bind to `127.0.0.1` only; metrics do
  not leave the host unless the collector exports them.
- GCP credentials live only in the collector container.
