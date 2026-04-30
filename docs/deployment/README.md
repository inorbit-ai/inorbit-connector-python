<!--
SPDX-FileCopyrightText: 2026 InOrbit, Inc.
SPDX-License-Identifier: MIT
-->

# Deploying metrics export for inorbit-connector

This directory holds a reference setup for collecting metrics from one or more
`inorbit-connector` containers on a single host and forwarding them to GCP
Cloud Monitoring.

## How it works

1. Each connector container runs a Prometheus-format HTTP endpoint bound to a
   configurable port (default `9090`). Under Docker bridge networking each
   container lives in its own network namespace, so a fixed port has no
   conflict.
2. Each connector writes a small JSON file to a shared Docker named volume
   (`inorbit-connector-metrics`). The file uses Prometheus `file_sd` format
   and names the connector's advertised address (for example `brand-1:9090`).
3. One OTEL collector runs alongside the connectors, mounts the same volume
   read-only, and uses `file_sd_configs` to discover every connector. It
   scrapes them and exports to GCP via the `googlecloud` exporter.

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
[Metrics user guide](../contents/usage/metrics.md).

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

- In GCP Cloud Monitoring, under Custom Metrics, look for
  `custom.googleapis.com/inorbit_connector/*` series.

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
