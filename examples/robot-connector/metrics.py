# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Connector-specific metrics for the example bot.

Declares one meter (``example_bot_connector``) with two counters that the
robot wrapper instruments. This is the minimum-viable alerting kit for a
concrete connector: count calls (so you know it's running) and count
failures (so you know when it's broken).
"""

from inorbit_edge.metrics import get_meter

meter = get_meter("example_bot_connector")

api_requests = meter.create_counter(
    "example_bot.api.requests",
    unit="1",
    description="Calls made to the example bot API (attribute: endpoint)",
)
api_errors = meter.create_counter(
    "example_bot.api.errors",
    unit="1",
    description="Failures calling the example bot API (attribute: endpoint)",
)
