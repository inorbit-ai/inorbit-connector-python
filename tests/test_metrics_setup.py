# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

from unittest.mock import patch

import pytest
from opentelemetry import metrics as otel_metrics
from opentelemetry.metrics import _internal as otel_metrics_internal
from opentelemetry.sdk.metrics import MeterProvider

from inorbit_connector.models import MetricsConfig
from inorbit_connector.metrics import setup_prometheus_metrics


@pytest.fixture(autouse=True)
def _reset_global_meter_provider():
    """Reset OTEL global provider state after each test."""
    yield
    from opentelemetry.util._once import Once

    otel_metrics_internal._METER_PROVIDER = None
    otel_metrics_internal._PROXY_METER_PROVIDER = (
        otel_metrics_internal._ProxyMeterProvider()
    )
    otel_metrics_internal._METER_PROVIDER_SET_ONCE = Once()


def test_disabled_returns_false():
    cfg = MetricsConfig(enabled=False)
    assert setup_prometheus_metrics(cfg, "test", "test-1") is False


def test_missing_exporter_returns_false_and_logs(caplog):
    cfg = MetricsConfig(enabled=True)
    with patch("inorbit_edge.metrics.PROMETHEUS_EXPORTER_AVAILABLE", False):
        installed = setup_prometheus_metrics(cfg, "test", "test-1")
    assert installed is False
    assert any(
        "OpenTelemetry" in r.getMessage() or "Prometheus" in r.getMessage()
        for r in caplog.records
    )


def test_enabled_installs_provider_with_identity_attributes():
    cfg = MetricsConfig(
        enabled=True,
        exporter_namespace="inorbit_connector",
        extra_resource_attributes={"site": "lab"},
    )
    assert setup_prometheus_metrics(cfg, "brand-1", "rId-1") is True

    provider = otel_metrics.get_meter_provider()
    assert isinstance(provider, MeterProvider)
    attrs = dict(provider._sdk_config.resource.attributes)
    assert attrs["service.name"] == "inorbit_connector"
    assert attrs["service.instance.id"] == "rId-1"
    assert attrs["inorbit.connector.type"] == "brand-1"
    assert attrs["inorbit.connector.id"] == "rId-1"
    assert attrs["site"] == "lab"
    assert "service.version" in attrs


def test_enabled_derives_namespace_from_connector_type_when_unset():
    cfg = MetricsConfig(enabled=True)  # exporter_namespace left at None
    assert setup_prometheus_metrics(cfg, "acme", "rId-1") is True

    provider = otel_metrics.get_meter_provider()
    attrs = dict(provider._sdk_config.resource.attributes)
    # service.name is the wire-level prefix; the prom exporter prepends
    # it to every metric. With connector_type="acme" the derived value
    # gives `inorbit_acme_connector_*` on the wire.
    assert attrs["service.name"] == "inorbit_acme_connector"
