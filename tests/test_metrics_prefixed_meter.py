# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock

import pytest

from inorbit_connector.metrics import PrefixedMeter, get_connector_meter


def test_prefixed_meter_prepends_prefix_to_counter_name():
    underlying = MagicMock()
    meter = PrefixedMeter(underlying, "acme.")

    meter.create_counter("mission.failures", unit="1", description="d")

    underlying.create_counter.assert_called_once_with(
        "acme.mission.failures", unit="1", description="d"
    )


def test_prefixed_meter_prepends_prefix_to_every_instrument_type():
    underlying = MagicMock()
    meter = PrefixedMeter(underlying, "acme.")

    meter.create_up_down_counter("queue.depth")
    meter.create_histogram("api.duration")
    meter.create_gauge("battery.level")
    meter.create_observable_gauge("battery.observable", callbacks=[lambda _: []])
    meter.create_observable_counter("ticks.observable", callbacks=[lambda _: []])
    meter.create_observable_up_down_counter("ud.observable", callbacks=[lambda _: []])

    assert underlying.create_up_down_counter.call_args[0][0] == "acme.queue.depth"
    assert underlying.create_histogram.call_args[0][0] == "acme.api.duration"
    assert underlying.create_gauge.call_args[0][0] == "acme.battery.level"
    assert underlying.create_observable_gauge.call_args[0][0] == "acme.battery.observable"
    assert underlying.create_observable_counter.call_args[0][0] == "acme.ticks.observable"
    assert (
        underlying.create_observable_up_down_counter.call_args[0][0] == "acme.ud.observable"
    )


def test_prefixed_meter_forwards_unknown_attrs_to_underlying():
    underlying = MagicMock()
    underlying.some_attr = "value"
    meter = PrefixedMeter(underlying, "acme.")

    assert meter.some_attr == "value"


def test_get_connector_meter_returns_prefixed_meter():
    meter = get_connector_meter("acme")
    assert isinstance(meter, PrefixedMeter)
    assert meter._prefix == "acme."


def test_get_connector_meter_rejects_empty_connector_type():
    with pytest.raises(ValueError):
        get_connector_meter("")


def test_get_connector_meter_creates_instrument_with_prefixed_name(monkeypatch):
    underlying = MagicMock()
    monkeypatch.setattr(
        "inorbit_connector.metrics.get_meter", lambda _name: underlying
    )

    meter = get_connector_meter("acme")
    meter.create_counter("mission.failures")

    underlying.create_counter.assert_called_once_with("acme.mission.failures")
