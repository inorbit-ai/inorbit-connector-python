# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Connector-specific domain metrics for the example bot.

Upstream API call counts (success, error, latency) are handled by the
framework's canonical helpers in ``inorbit_connector.metrics.http`` — see
``robot.py`` for the call sites. This module is for domain instruments
the framework does NOT know about: things only this connector's logic
can detect.
"""

from inorbit_connector.metrics import get_connector_meter

# Vendor prefix is added structurally. The instrument name below is
# created on the underlying meter as ``example_bot.telemetry.invalid_response``
# and exports on the wire as
# ``inorbit_connector_example_bot_telemetry_invalid_response_total``.
meter = get_connector_meter("example_bot")

telemetry_invalid_response = meter.create_counter(
    "telemetry.invalid_response",
    unit="1",
    description=(
        "Telemetry responses dropped because a required field was missing "
        "(attribute: missing_field). Tracks API contract drift the framework "
        "cannot see — every increment indicates a payload the connector "
        "could not turn into a pose/odometry/system-stats publish."
    ),
)
