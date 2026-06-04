# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

import importlib
import logging
from unittest.mock import MagicMock

import pytest

from inorbit_connector.metrics import http as http_metrics
from inorbit_connector.metrics.http import (
    EndpointMapper,
    PathTemplater,
    record_upstream_http_error,
    record_upstream_http_request,
)


# --- record helpers -------------------------------------------------------


@pytest.fixture
def captured_instruments(monkeypatch):
    requests = MagicMock()
    errors = MagicMock()
    duration = MagicMock()
    monkeypatch.setattr(http_metrics, "upstream_http_requests", requests)
    monkeypatch.setattr(http_metrics, "upstream_http_errors", errors)
    monkeypatch.setattr(http_metrics, "upstream_http_duration", duration)
    return requests, errors, duration


def test_record_request_increments_counter_and_observes_duration(captured_instruments):
    requests, errors, duration = captured_instruments

    record_upstream_http_request(
        vendor="acme",
        method="GET",
        endpoint="missions",
        duration_seconds=0.123,
    )

    requests.add.assert_called_once_with(
        1, {"vendor": "acme", "method": "GET", "endpoint": "missions"}
    )
    duration.record.assert_called_once_with(
        0.123, {"vendor": "acme", "method": "GET", "endpoint": "missions"}
    )
    errors.add.assert_not_called()


def test_record_error_increments_error_counter_with_error_kind(captured_instruments):
    requests, errors, duration = captured_instruments

    record_upstream_http_error(
        vendor="acme",
        method="POST",
        endpoint="missions",
        error_kind="timeout",
        duration_seconds=2.5,
    )

    errors.add.assert_called_once_with(
        1,
        {
            "vendor": "acme",
            "method": "POST",
            "endpoint": "missions",
            "error_kind": "timeout",
        },
    )
    # Duration attrs do NOT carry error_kind — keeps the histogram descriptor small.
    duration.record.assert_called_once_with(
        2.5, {"vendor": "acme", "method": "POST", "endpoint": "missions"}
    )
    requests.add.assert_not_called()


def test_record_error_coerces_unknown_error_kind_to_other(captured_instruments, caplog):
    requests, errors, duration = captured_instruments
    caplog.set_level(logging.WARNING, logger=http_metrics.__name__)

    record_upstream_http_error(
        vendor="acme",
        method="GET",
        endpoint="missions",
        error_kind="banana",
        duration_seconds=0.1,
    )

    # Out-of-set value must NOT reach the descriptor — coerced to 'other'.
    errors.add.assert_called_once_with(
        1,
        {
            "vendor": "acme",
            "method": "GET",
            "endpoint": "missions",
            "error_kind": "other",
        },
    )
    assert any("error_kind=" in r.getMessage() for r in caplog.records)


def test_record_request_warns_when_endpoint_looks_unbounded(
    captured_instruments, caplog
):
    caplog.set_level(logging.WARNING, logger=http_metrics.__name__)
    record_upstream_http_request(
        vendor="acme",
        method="GET",
        endpoint="/api/v1/missions/123/result",
        duration_seconds=0.1,
    )
    # Counter still recorded — warning is advisory, not a guard.
    assert any("looks like a raw path" in r.getMessage() for r in caplog.records)


def test_module_imports_with_real_no_op_meter():
    # Re-importing the module must not raise even when no MeterProvider is set.
    importlib.reload(http_metrics)


# --- EndpointMapper -------------------------------------------------------


class TestEndpointMapper:
    def test_matches_known_prefix(self):
        m = EndpointMapper(
            [
                ("/api/v1/missions", "missions"),
                ("/api/v1/status", "status"),
            ]
        )
        assert m("/api/v1/missions/abc-123/result") == "missions"
        assert m("/api/v1/status") == "status"

    def test_longest_prefix_wins(self):
        m = EndpointMapper(
            [
                ("/api/v1/missions", "missions"),
                ("/api/v1/missions/queue", "missions_queue"),
            ]
        )
        assert m("/api/v1/missions/queue/items") == "missions_queue"
        assert m("/api/v1/missions/abc/result") == "missions"

    def test_unknown_falls_back_to_default_label(self):
        m = EndpointMapper([("/api/v1/missions", "missions")])
        assert m("/api/v1/unknown") == "other"

    def test_unknown_label_override(self):
        m = EndpointMapper(
            [("/api/v1/missions", "missions")],
            unknown_label="UNKNOWN",
        )
        assert m("/v2/orders") == "UNKNOWN"


# --- PathTemplater --------------------------------------------------------


class TestPathTemplater:
    def setup_method(self):
        self.t = PathTemplater()

    def test_masks_uuid(self):
        out = self.t("missions/123e4567-e89b-12d3-a456-426614174000/result")
        assert out == "missions/{id}/result"

    def test_masks_numeric_segment(self):
        assert self.t("orders/42") == "orders/{id}"

    def test_masks_long_hex(self):
        assert self.t("blobs/abcdef0123456789abcdef0123") == "blobs/{id}"

    def test_masks_dashed_id(self):
        assert self.t("missions/abc-123-def/result") == "missions/{id}/result"

    def test_keeps_pure_word_segments(self):
        assert self.t("status") == "status"
        assert self.t("missions/queue") == "missions/queue"

    def test_preserves_leading_slash(self):
        assert self.t("/orders/42") == "/orders/{id}"
        assert self.t("orders/42") == "orders/{id}"

    def test_empty_path_returns_empty(self):
        assert self.t("") == ""

    def test_short_hex_word_is_not_masked(self):
        # "abc" alone (< 16 chars hex, no digit) stays as-is.
        assert self.t("orders/abc") == "orders/abc"
