# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Connector-specific metrics for the example bot fleet.

The fleet manager API is bulk — one HTTP call returns data for many robots —
so wire-level counters are scoped per endpoint. ``robot_updates_received``
fans the response out to a per-robot counter so you can spot a single robot
silently dropping out of the fleet API's response. Per-robot MQTT-side
counters are inherited from the inorbit-edge SDK
(``calls_publish_*_total{robot_id=...}``).
"""

from inorbit_edge.metrics import get_meter

meter = get_meter("example_bot_fleet_connector")

fleet_api_requests = meter.create_counter(
    "example_bot.fleet_api.requests",
    unit="1",
    description="HTTP calls to the fleet manager API (attribute: endpoint)",
)
fleet_api_errors = meter.create_counter(
    "example_bot.fleet_api.errors",
    unit="1",
    description="Failed HTTP calls to the fleet manager API (attribute: endpoint)",
)
robot_updates_received = meter.create_counter(
    "example_bot.robot.updates_received",
    unit="1",
    description=(
        "Data points received from the fleet API, fanned out per robot "
        "(attributes: endpoint, robot_id)"
    ),
)
