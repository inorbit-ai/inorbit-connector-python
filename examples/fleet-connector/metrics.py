# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Connector-specific metrics for the example bot fleet.

The fleet manager API is one upstream that returns data for many robots in
each call, so the counters here are scoped per endpoint, not per robot.
Per-robot publish counters are inherited from the inorbit-edge SDK
(``calls_publish_*_total{robot_id=...}``).
"""

from inorbit_edge.metrics import get_meter

meter = get_meter("example_bot_fleet_connector")

fleet_api_requests = meter.create_counter(
    "example_bot.fleet_api.requests",
    unit="1",
    description="Calls made to the fleet manager API (attribute: endpoint)",
)
fleet_api_errors = meter.create_counter(
    "example_bot.fleet_api.errors",
    unit="1",
    description="Failures calling the fleet manager API (attribute: endpoint)",
)
