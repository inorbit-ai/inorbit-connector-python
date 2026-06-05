# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Connector-specific domain metrics for the example bot fleet.

Upstream API call counts (success, error, latency) are handled by the
framework's canonical helpers in ``inorbit_connector.metrics.http`` — see
``fleet_client.py`` for the call sites. This module owns the one signal
the canonical helpers cannot see: the fleet API is bulk (one call returns
data for many robots), so a per-robot counter fanned out from the
response lets you spot a single robot silently dropping out of the fleet
API's payload even when the HTTP call keeps succeeding.
"""

from inorbit_connector.metrics import get_connector_meter

# Vendor prefix is added structurally. Instrument name below is created on
# the underlying meter as ``example_bot_fleet.robot.updates_received`` and
# exports on the wire as
# ``inorbit_connector_example_bot_fleet_robot_updates_received_total``.
meter = get_connector_meter("example_bot_fleet")

robot_updates_received = meter.create_counter(
    "robot.updates_received",
    unit="1",
    description=(
        "Data points received from the fleet API, fanned out per robot "
        "(attributes: endpoint, robot_id). Increments once per robot per "
        "bulk API response, so a robot missing from the payload shows up "
        "as a drop in its individual rate."
    ),
)
