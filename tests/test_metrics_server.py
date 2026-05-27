# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

import json
import socket
import urllib.request

import pytest
from opentelemetry.metrics import _internal as otel_metrics_internal

from inorbit_connector.models import MetricsConfig
from inorbit_connector.metrics import MetricsServer, setup_prometheus_metrics


@pytest.fixture(autouse=True)
def _reset_otel_global():
    yield
    from opentelemetry.util._once import Once

    otel_metrics_internal._METER_PROVIDER = None
    otel_metrics_internal._PROXY_METER_PROVIDER = (
        otel_metrics_internal._ProxyMeterProvider()
    )
    otel_metrics_internal._METER_PROVIDER_SET_ONCE = Once()


@pytest.fixture
def metrics_enabled(tmp_path):
    cfg = MetricsConfig(
        enabled=True,
        bind_host="127.0.0.1",
        bind_port=0,
        advertise_host="127.0.0.1",
        discovery_dir=tmp_path,
        connector_id="test-1",
    )
    setup_prometheus_metrics(cfg, connector_type="test", connector_id="test-1")
    yield cfg


def test_server_serves_metrics_endpoint(metrics_enabled):
    cfg = metrics_enabled
    server = MetricsServer(config=cfg, connector_id="test-1")
    server.start()
    try:
        assert server.actual_port is not None and server.actual_port > 0
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.actual_port}/metrics", timeout=5
        ) as resp:
            assert resp.status == 200
            resp.read()
    finally:
        server.stop()


def test_server_writes_discovery_file_atomically(metrics_enabled, tmp_path):
    cfg = metrics_enabled
    server = MetricsServer(config=cfg, connector_id="test-1")
    server.start()
    try:
        discovery_path = tmp_path / "test-1.json"
        assert discovery_path.exists()
        data = json.loads(discovery_path.read_text())
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["targets"] == [f"127.0.0.1:{server.actual_port}"]
        assert data[0]["labels"] == {}
    finally:
        server.stop()
    assert not discovery_path.exists()


def test_server_creates_discovery_dir_when_missing(metrics_enabled, tmp_path):
    nested = tmp_path / "deeper" / "nested"
    cfg = metrics_enabled
    cfg.discovery_dir = nested
    server = MetricsServer(config=cfg, connector_id="test-1")
    server.start()
    try:
        assert nested.is_dir()
        assert (nested / "test-1.json").exists()
    finally:
        server.stop()


def test_server_handles_port_bind_failure(metrics_enabled, tmp_path, caplog):
    cfg = metrics_enabled
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        cfg.bind_port = port
        server = MetricsServer(config=cfg, connector_id="test-1")
        server.start()
        assert server.actual_port is None
        assert not (tmp_path / "test-1.json").exists()
        assert any("bind" in r.getMessage().lower() for r in caplog.records)
        server.stop()
    finally:
        sock.close()


def test_server_atomic_write_uses_tmp_rename(monkeypatch, metrics_enabled):
    cfg = metrics_enabled
    server = MetricsServer(config=cfg, connector_id="test-1")

    calls = []
    import os as _os

    real_replace = _os.replace

    def _spy_replace(src, dst):
        calls.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr("os.replace", _spy_replace)
    server.start()
    try:
        assert calls, "os.replace was not called"
        src, dst = calls[-1]
        assert src.endswith(".json.tmp")
        assert dst.endswith("test-1.json")
    finally:
        server.stop()


def test_server_skips_discovery_when_dir_is_none(metrics_enabled, tmp_path):
    """discovery_dir=None: HTTP endpoint still serves, but no file is written."""
    cfg = metrics_enabled
    cfg.discovery_dir = None
    server = MetricsServer(config=cfg, connector_id="test-1")
    server.start()
    try:
        assert server.actual_port is not None and server.actual_port > 0
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.actual_port}/metrics", timeout=5
        ) as resp:
            assert resp.status == 200
        assert not (tmp_path / "test-1.json").exists()
    finally:
        server.stop()


def test_stop_closes_server_socket_and_joins_thread(metrics_enabled):
    """stop() must call server_close() and join the background thread so the
    listening port is freed promptly."""
    cfg = metrics_enabled
    server = MetricsServer(config=cfg, connector_id="test-1")
    server.start()
    httpd = server._http_server
    thread = server._http_thread
    assert httpd is not None and thread is not None and thread.is_alive()

    server.stop()

    # Thread is joined and the socket file descriptor is closed.
    assert not thread.is_alive()
    assert httpd.socket.fileno() == -1
    # State is fully cleared.
    assert server._http_server is None
    assert server._http_thread is None
    assert server.actual_port is None
