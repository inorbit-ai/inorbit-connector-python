# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

import time
import urllib.request

import pytest
from opentelemetry.metrics import _internal as otel_metrics_internal

from inorbit_connector.connector import FleetConnector
from inorbit_connector.models import (
    ConnectorRootConfig,
    ConnectorSpecificConfig,
    MetricsConfig,
    RobotConfig,
)


class _MinimalConnectorRootConfig(ConnectorSpecificConfig):
    CONNECTOR_TYPE = "minimal"


class _MinimalConnector(FleetConnector):
    async def _connect(self):
        pass

    async def _disconnect(self):
        pass

    async def _execution_loop(self):
        pass

    async def _inorbit_robot_command_handler(
        self, robot_id, command_name, args, options
    ):
        pass


def _make_config(tmp_path, **overrides):
    base = dict(
        api_key="ak",
        connector_type="test",
        connector_config=_MinimalConnectorRootConfig(),
        fleet=[RobotConfig(robot_id="r1")],
        metrics=MetricsConfig(
            enabled=True,
            bind_host="127.0.0.1",
            bind_port=0,
            advertise_host="127.0.0.1",
            discovery_dir=tmp_path,
            connector_id="test-1",
        ),
    )
    base.update(overrides)
    return ConnectorRootConfig(**base)


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
def patched_run_connector(monkeypatch):
    """Replace the connector run thread target with a no-op."""
    monkeypatch.setattr(
        "inorbit_connector.connector.FleetConnector." "_FleetConnector__run_connector",
        lambda self: None,
    )


def test_metrics_server_lifecycle(tmp_path, patched_run_connector):
    cfg = _make_config(tmp_path)
    conn = _MinimalConnector(cfg)

    try:
        conn.start()
        time.sleep(0.2)
        port = conn._metrics_server.actual_port
        assert port is not None
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/metrics", timeout=5
        ) as resp:
            body = resp.read().decode()
        assert resp.status == 200
        # connector_type="test" → derived namespace `inorbit_test_connector_*`.
        assert "inorbit_test_connector_up" in body
    finally:
        conn.stop()


def test_metrics_disabled_by_default(tmp_path, patched_run_connector):
    cfg = ConnectorRootConfig(
        api_key="ak",
        connector_type="test",
        connector_config=_MinimalConnectorRootConfig(),
        fleet=[RobotConfig(robot_id="r1")],
    )
    conn = _MinimalConnector(cfg)
    assert conn._metrics_server is None
