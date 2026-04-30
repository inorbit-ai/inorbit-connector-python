# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

import json
import logging
import os
import socket
from pathlib import Path
from typing import Optional

from inorbit_connector.models import MetricsConfig


try:
    from prometheus_client import start_http_server

    _PROMETHEUS_CLIENT_AVAILABLE = True
except ImportError:
    start_http_server = None  # type: ignore[assignment]
    _PROMETHEUS_CLIENT_AVAILABLE = False


_logger = logging.getLogger(__name__)


class MetricsServer:
    """HTTP server + Prometheus file_sd discovery writer.

    Lifecycle:
        * ``start()`` binds the HTTP server, captures the actually bound
          port, and writes the discovery file atomically.
        * ``stop()`` shuts down the HTTP server and removes the discovery
          file.

    Both methods degrade silently with a log entry if something goes wrong.
    """

    def __init__(self, config: MetricsConfig, connector_id: str) -> None:
        self._config = config
        self._connector_id = connector_id
        self._http_server = None
        self._http_thread = None
        self.actual_port: Optional[int] = None

    def start(self) -> None:
        if not _PROMETHEUS_CLIENT_AVAILABLE:
            _logger.warning(
                "prometheus_client is not installed; metrics HTTP server will "
                "not start."
            )
            return

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
                _logger.error(
                    "Error shutting down metrics HTTP server: %s", exc
                )
            self._http_server = None
            self._http_thread = None

        discovery_path = self._discovery_file_path()
        try:
            if discovery_path.exists():
                discovery_path.unlink()
        except Exception as exc:
            _logger.error(
                "Failed to remove metrics discovery file %s: %s",
                discovery_path,
                exc,
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
        assert self.actual_port is not None

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
