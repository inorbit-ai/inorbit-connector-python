# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

import logging
from unittest.mock import MagicMock

import pytest

from inorbit_connector import metrics as m


@pytest.fixture
def captured_meter(monkeypatch):
    """Replace the module-level meter so we can capture registered callbacks."""
    fake_meter = MagicMock()
    monkeypatch.setattr(m, "meter", fake_meter)
    return fake_meter


def _registered_callback(fake_meter, name):
    """Return the single callback registered for the gauge `name`."""
    for call in fake_meter.create_observable_gauge.call_args_list:
        if call.args and call.args[0] == name:
            return call.kwargs["callbacks"][0]
        if call.kwargs.get("name") == name:
            return call.kwargs["callbacks"][0]
    raise AssertionError(f"no observable gauge registered with name {name!r}")


# --- robot.info -------------------------------------------------------------


class TestRobotInfoGauge:
    def test_emits_one_observation_per_robot_with_identity_labels(
        self, captured_meter
    ):
        info = {
            "r1": {"model": "MiR250", "firmware_version": "2.13.1"},
            "r2": {"model": "MiR100", "firmware_version": "2.9.0"},
        }
        m.register_robot_info_gauge(lambda: ["r1", "r2"], lambda rid: info[rid])

        observations = _registered_callback(captured_meter, "robot.info")(None)

        assert len(observations) == 2
        by_robot = {o.attributes["robot_id"]: o for o in observations}
        assert by_robot["r1"].value == 1
        assert by_robot["r1"].attributes["model"] == "MiR250"
        assert by_robot["r1"].attributes["firmware_version"] == "2.13.1"
        assert by_robot["r2"].attributes["model"] == "MiR100"

    def test_robot_with_unknown_info_is_omitted(self, captured_meter):
        info = {"r1": {"model": "MiR250"}, "r2": None}
        m.register_robot_info_gauge(lambda: ["r1", "r2"], lambda rid: info[rid])

        observations = _registered_callback(captured_meter, "robot.info")(None)

        assert len(observations) == 1
        assert observations[0].attributes["robot_id"] == "r1"

    def test_partial_info_emits_only_known_keys(self, captured_meter):
        m.register_robot_info_gauge(
            lambda: ["r1"], lambda _rid: {"model": "Nipper"}
        )

        observations = _registered_callback(captured_meter, "robot.info")(None)

        assert observations[0].attributes == {"robot_id": "r1", "model": "Nipper"}

    def test_unknown_keys_are_dropped_with_warning(self, captured_meter, caplog):
        caplog.set_level(logging.WARNING, logger=m.__name__)
        m.register_robot_info_gauge(
            lambda: ["r1"],
            lambda _rid: {"model": "MiR250", "serial_number": "abc-123"},
        )

        observations = _registered_callback(captured_meter, "robot.info")(None)

        assert observations[0].attributes == {"robot_id": "r1", "model": "MiR250"}
        assert any("serial_number" in r.getMessage() for r in caplog.records)

    def test_empty_values_are_dropped(self, captured_meter):
        m.register_robot_info_gauge(
            lambda: ["r1"],
            lambda _rid: {"model": "", "firmware_version": "2.13.1"},
        )

        observations = _registered_callback(captured_meter, "robot.info")(None)

        assert observations[0].attributes == {
            "robot_id": "r1",
            "firmware_version": "2.13.1",
        }

    def test_robot_with_only_unknown_or_empty_attrs_is_omitted(self, captured_meter):
        m.register_robot_info_gauge(
            lambda: ["r1"], lambda _rid: {"serial_number": "abc", "model": ""}
        )

        observations = _registered_callback(captured_meter, "robot.info")(None)

        assert observations == []

    def test_fleet_membership_is_read_per_scrape(self, captured_meter):
        fleet = ["r1"]
        m.register_robot_info_gauge(
            lambda: fleet, lambda _rid: {"model": "MiR250"}
        )
        callback = _registered_callback(captured_meter, "robot.info")

        assert len(callback(None)) == 1
        fleet.append("r2")  # robot added at runtime (fleet autodiscovery)
        assert len(callback(None)) == 2


# --- fleet_manager.info -------------------------------------------------------


class TestFleetManagerInfoGauge:
    def test_emits_single_observation_with_version_label(self, captured_meter):
        m.register_fleet_manager_info_gauge(lambda: "3.4.0")

        observations = _registered_callback(captured_meter, "fleet_manager.info")(
            None
        )

        assert len(observations) == 1
        assert observations[0].value == 1
        assert observations[0].attributes == {"version": "3.4.0"}

    def test_unknown_version_emits_nothing(self, captured_meter):
        m.register_fleet_manager_info_gauge(lambda: None)

        observations = _registered_callback(captured_meter, "fleet_manager.info")(
            None
        )

        assert observations == []

    def test_version_is_read_per_scrape(self, captured_meter):
        versions = iter(["3.4.0", "3.5.0"])
        m.register_fleet_manager_info_gauge(lambda: next(versions))
        callback = _registered_callback(captured_meter, "fleet_manager.info")

        assert callback(None)[0].attributes == {"version": "3.4.0"}
        # Upstream upgraded between scrapes — the label value follows.
        assert callback(None)[0].attributes == {"version": "3.5.0"}
