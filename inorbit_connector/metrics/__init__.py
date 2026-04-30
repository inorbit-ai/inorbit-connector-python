# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

"""OpenTelemetry metrics for inorbit-connector.

This module ships the minimum framework-level signals needed to alert on
connector health and provides one entry point — :func:`setup_prometheus_metrics`
— that wires up Prometheus export from a :class:`MetricsConfig`.

Framework instruments (always declared, no-op when metrics are disabled):

* ``inorbit.connector.up`` — 1 while the connector's main thread is alive
* ``inorbit.connector.session.connected`` — per-robot MQTT connection status (1/0)
* ``inorbit.connector.execution_loop.ticks`` — successful run-loop iterations
* ``inorbit.connector.execution_loop.errors`` — exceptions caught in the loop

For domain metrics (e.g. ``fleet.api.errors``, ``mqtt.broker.connected``),
concrete connectors get their own meter via
``inorbit_edge.metrics.get_meter("inorbit_<vendor>_connector")`` and declare
instruments on it. They share the global MeterProvider installed here, so
everything flows through the same Prometheus endpoint.

The Prometheus exporter ships transitively via ``inorbit-edge[telemetry]``,
which is a base dependency of this package, so OTEL is always importable.
:func:`setup_prometheus_metrics` returns ``False`` when ``metrics.enabled``
is ``False`` (the default); when False, no provider is installed and no
HTTP server is started.
"""

import json
import logging
import os
import socket
from pathlib import Path

from inorbit_edge.metrics import (
    OTEL_API_AVAILABLE,
    Observation,
    get_meter,
    setup_prometheus_meter_provider,
)
from prometheus_client import start_http_server

from inorbit_connector import __version__ as _connector_version
from inorbit_connector.models import MetricsConfig


_logger = logging.getLogger(__name__)


# --- Provider setup -------------------------------------------------------


def setup_prometheus_metrics(
    config: MetricsConfig,
    connector_type: str,
    connector_id: str,
) -> bool:
    """Install the global Prometheus-exporting MeterProvider for this process.

    Thin adapter over :func:`inorbit_edge.metrics.setup_prometheus_meter_provider`
    that maps :class:`MetricsConfig` to the SDK call. Returns True when a
    provider was installed; False when metrics are disabled or the telemetry
    dependencies are missing.
    """
    if not config.enabled:
        return False

    installed = setup_prometheus_meter_provider(
        service_name=config.exporter_namespace,
        service_instance_id=connector_id,
        service_version=_connector_version,
        extra_resource_attributes={
            "inorbit.connector.type": connector_type,
            "inorbit.connector.id": connector_id,
            **config.extra_resource_attributes,
        },
    )
    if not installed:
        _logger.warning(
            "Metrics enabled but the OpenTelemetry / Prometheus exporter "
            "dependencies are not installed. Reinstall this package to "
            "pick up inorbit-edge[telemetry]."
        )
    return installed


# --- HTTP server + file_sd discovery file ---------------------------------


class MetricsServer:
    """Prometheus HTTP server + ``file_sd``-format discovery writer.

    The HTTP-serving piece is one call to ``prometheus_client.start_http_server``;
    the value-add of this class is the discovery file. On ``start()`` the
    connector writes ``<discovery_dir>/<connector_id>.json`` (atomic
    tmp-and-rename) describing its bound ``host:port`` so a host-side OTEL
    collector can pick it up via ``file_sd_configs``. ``stop()`` removes the
    file and shuts the HTTP server down.

    Both methods degrade silently with a log entry if something goes wrong.
    """

    def __init__(self, config: MetricsConfig, connector_id: str) -> None:
        self._config = config
        self._connector_id = connector_id
        self._http_server = None
        self._http_thread = None
        self.actual_port: int | None = None

    def start(self) -> None:
        try:
            self._http_server, self._http_thread = start_http_server(
                port=self._config.bind_port,
                addr=self._config.bind_host,
            )
            self.actual_port = self._http_server.server_address[1]
        except Exception as exc:
            _logger.error(
                "Failed to bind metrics HTTP server on %s:%s: %s",
                self._config.bind_host,
                self._config.bind_port,
                exc,
            )
            self._http_server = None
            self._http_thread = None
            self.actual_port = None
            return

        try:
            self._write_discovery_file()
        except Exception as exc:
            _logger.error("Failed to write metrics discovery file: %s", exc)

    def stop(self) -> None:
        if self._http_server is not None:
            try:
                self._http_server.shutdown()
            except Exception as exc:
                _logger.error("Error shutting down metrics HTTP server: %s", exc)
            self._http_server = None
            self._http_thread = None

        path = self._discovery_file_path()
        try:
            if path.exists():
                path.unlink()
        except Exception as exc:
            _logger.error(
                "Failed to remove metrics discovery file %s: %s", path, exc
            )

    def _discovery_file_path(self) -> Path:
        return Path(self._config.discovery_dir) / f"{self._connector_id}.json"

    def _write_discovery_file(self) -> None:
        discovery_dir = Path(self._config.discovery_dir)
        discovery_dir.mkdir(parents=True, exist_ok=True)

        advertise_host = (
            self._config.advertise_host
            or socket.gethostname()
            or "localhost"
        )
        body = [
            {
                "targets": [f"{advertise_host}:{self.actual_port}"],
                "labels": {},
            }
        ]
        path = self._discovery_file_path()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(body) + "\n")
        os.replace(tmp, path)


# --- Framework instruments ------------------------------------------------

meter = get_meter("inorbit_connector")

execution_loop_ticks = meter.create_counter(
    "inorbit.connector.execution_loop.ticks",
    unit="1",
    description="Successful iterations of the connector's _execution_loop",
)
execution_loop_errors = meter.create_counter(
    "inorbit.connector.execution_loop.errors",
    unit="1",
    description="Exceptions caught in the run loop",
)


def register_framework_gauges(
    is_alive,
    robot_ids,
    is_session_connected,
) -> None:
    """Register the framework-level ObservableGauges.

    All callbacks run on every Prometheus scrape, so they should be cheap
    and side-effect free. No-ops when the OTEL API is not installed.

    Args:
        is_alive: zero-arg callable returning whether the connector's main
            thread is alive. Drives ``inorbit.connector.up``.
        robot_ids: zero-arg callable returning the current list of robot ids
            in the fleet.
        is_session_connected: callable ``(robot_id: str) -> bool`` that
            returns whether the underlying MQTT session for that robot is
            currently connected. Drives
            ``inorbit.connector.session.connected``. Should swallow lookup
            errors and return False when the session is not yet available.
    """
    if not OTEL_API_AVAILABLE:
        return

    def _up_callback(_options):
        return [Observation(1 if is_alive() else 0)]

    def _session_callback(_options):
        return [
            Observation(
                1 if is_session_connected(rid) else 0,
                {"robot_id": rid},
            )
            for rid in robot_ids()
        ]

    meter.create_observable_gauge(
        "inorbit.connector.up",
        callbacks=[_up_callback],
        unit="1",
        description="1 while the connector main thread is alive",
    )
    meter.create_observable_gauge(
        "inorbit.connector.session.connected",
        callbacks=[_session_callback],
        unit="1",
        description=(
            "Per-robot MQTT session connection status (1 = connected, "
            "0 = disconnected). Captures the case where the connector "
            "process is alive but its MQTT link to InOrbit is down."
        ),
    )
