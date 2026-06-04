# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

"""Canonical upstream-HTTP metric family for connector vendors.

Concrete connectors record every outbound HTTP call to their upstream API
through :func:`record_upstream_http_request` (success path) and
:func:`record_upstream_http_error` (any failure path). Both helpers write
to a fixed set of framework instruments with a frozen attribute schema:

* ``inorbit.connector.upstream.http.requests`` — counter, success path
* ``inorbit.connector.upstream.http.errors`` — counter, error path
* ``inorbit.connector.upstream.http.duration`` — histogram, both paths

Why the split: failures are rare, so keeping ``error_kind`` off the success
counter lets the success descriptor stay at three attributes and the error
descriptor's label space grow slowly. Total throughput is
``requests + errors``; error rate is ``errors / (requests + errors)``.

The ``endpoint`` attribute is the #1 cardinality footgun. Always normalize
the raw path through :class:`EndpointMapper` (preferred for stable APIs)
or :class:`PathTemplater` (preferred for evolving APIs) before passing it
to either helper.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from inorbit_edge.metrics import get_meter

from inorbit_connector.metrics import EXPORTER_NAMESPACE


_logger = logging.getLogger(__name__)


# --- Instruments ----------------------------------------------------------

# Module-level so OTEL ties them to the framework provider once it's installed.
# Until then they're no-op (lazy proxy) and stay correct.
_meter = get_meter(EXPORTER_NAMESPACE)

# 7 explicit boundaries → 9 series per attribute combination (vs. 18 for OTEL's
# default), tuned for typical upstream-API latencies (50 ms – 5 s). Increase
# only if your API regularly runs slower; do not extend without a reason.
_LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

upstream_http_requests = _meter.create_counter(
    "upstream.http.requests",
    unit="1",
    description=(
        "Successful upstream HTTP calls (2xx/3xx responses). Attributes: "
        "vendor, method, endpoint. Failures go to upstream.http.errors."
    ),
)
upstream_http_errors = _meter.create_counter(
    "upstream.http.errors",
    unit="1",
    description=(
        "Failed upstream HTTP calls (timeout, connect error, non-2xx). "
        "Attributes: vendor, method, endpoint, error_kind."
    ),
)
upstream_http_duration = _meter.create_histogram(
    "upstream.http.duration",
    unit="s",
    description=(
        "Latency of upstream HTTP calls, recorded on both success and error "
        "paths. Attributes: vendor, method, endpoint."
    ),
    explicit_bucket_boundaries_advisory=_LATENCY_BUCKETS,
)


# --- Recording helpers ----------------------------------------------------

_ALLOWED_ERROR_KINDS = {
    "timeout",
    "connect_error",
    "http_4xx",
    "http_5xx",
    "other",
}


def _warn_unbounded_endpoint(endpoint: str) -> None:
    # Raw paths usually contain both a slash and a digit (e.g. an ID
    # segment). The guard is a heuristic and intentionally non-blocking — it
    # exists to nudge authors toward EndpointMapper/PathTemplater before a
    # descriptor gets polluted. False positives are acceptable; the
    # remediation (use a normalizer) is the same either way.
    if "/" in endpoint and any(ch.isdigit() for ch in endpoint):
        _logger.warning(
            "upstream.http endpoint=%r looks like a raw path; normalize via "
            "EndpointMapper or PathTemplater to avoid descriptor cardinality "
            "explosion",
            endpoint,
        )


def record_upstream_http_request(
    *,
    vendor: str,
    method: str,
    endpoint: str,
    duration_seconds: float,
) -> None:
    """Record one successful upstream HTTP call (2xx/3xx).

    Bumps ``upstream.http.requests`` by 1 and observes ``duration_seconds``
    on ``upstream.http.duration``. Use :func:`record_upstream_http_error`
    for any non-2xx response, timeout, or connect failure.

    Args:
        vendor: Connector type (e.g. ``"acme"``). Must equal
            ``ConnectorRootConfig.connector_type``.
        method: HTTP method in upper case (``"GET"``, ``"POST"``, ...).
        endpoint: Normalized endpoint label. Pass the output of an
            :class:`EndpointMapper` or :class:`PathTemplater`, NOT a raw
            URL path.
        duration_seconds: Wall-clock duration of the request in seconds.
    """
    _warn_unbounded_endpoint(endpoint)
    attrs = {"vendor": vendor, "method": method, "endpoint": endpoint}
    upstream_http_requests.add(1, attrs)
    upstream_http_duration.record(duration_seconds, attrs)


def record_upstream_http_error(
    *,
    vendor: str,
    method: str,
    endpoint: str,
    error_kind: str,
    duration_seconds: float,
) -> None:
    """Record one failed upstream HTTP call.

    Bumps ``upstream.http.errors`` by 1 and observes ``duration_seconds`` on
    ``upstream.http.duration`` (the same histogram as the success path, so
    p99 latency reflects every call regardless of outcome).

    Args:
        vendor: Connector type (e.g. ``"acme"``). Must equal
            ``ConnectorRootConfig.connector_type``.
        method: HTTP method in upper case.
        endpoint: Normalized endpoint label. See :func:`record_upstream_http_request`.
        error_kind: Bounded enum. One of ``"timeout"``, ``"connect_error"``,
            ``"http_4xx"``, ``"http_5xx"``, ``"other"``. Values outside the
            set are coerced to ``"other"`` (with a WARNING) so the
            descriptor's label space stays bounded — do not invent new
            kinds without updating the framework.
        duration_seconds: Wall-clock duration of the failed request.
    """
    if error_kind not in _ALLOWED_ERROR_KINDS:
        _logger.warning(
            "upstream.http error_kind=%r is outside the bounded set %s; "
            "coercing to 'other' to keep the descriptor bounded",
            error_kind,
            sorted(_ALLOWED_ERROR_KINDS),
        )
        error_kind = "other"
    _warn_unbounded_endpoint(endpoint)
    duration_attrs = {"vendor": vendor, "method": method, "endpoint": endpoint}
    upstream_http_errors.add(1, {**duration_attrs, "error_kind": error_kind})
    upstream_http_duration.record(duration_seconds, duration_attrs)


# --- Endpoint normalizers -------------------------------------------------


class EndpointMapper:
    """Map raw HTTP paths to bounded labels via an explicit prefix table.

    Use this for stable APIs where you can enumerate the route families.
    Construct once at module load — typically alongside your API client —
    and call as a function on every request path::

        _endpoint = EndpointMapper([
            ("/api/v1/missions",      "missions"),
            ("/api/v1/mission_queue", "mission_queue"),
            ("/api/v1/status",        "status"),
        ])
        _endpoint("/api/v1/missions/abc-123/result")  # -> "missions"
        _endpoint("/api/v1/unknown")                   # -> "other"

    Matching is by longest prefix. Unknown paths collapse to the
    ``unknown_label`` value (default ``"other"``) so the cardinality stays
    bounded by the number of declared routes, not by the universe of paths
    the upstream API can return.
    """

    def __init__(
        self,
        routes: Iterable[tuple[str, str]],
        unknown_label: str = "other",
    ) -> None:
        # Sort by prefix length descending so "/api/v1/missions/queue" wins
        # over "/api/v1/missions" when both match.
        self._routes = sorted(routes, key=lambda p: -len(p[0]))
        self._unknown_label = unknown_label

    def __call__(self, path: str) -> str:
        for prefix, label in self._routes:
            if path.startswith(prefix):
                return label
        return self._unknown_label


class PathTemplater:
    """Mask high-cardinality path segments by pattern.

    Use this for evolving APIs where maintaining an explicit route table is
    impractical. Segments matching UUIDs, long hex strings, or pure
    numbers are replaced with the literal ``{id}``::

        t = PathTemplater()
        t("missions/abc-123-def/result")  # -> "missions/{id}/result"
        t("orders/42")                     # -> "orders/{id}"
        t("status")                        # -> "status"

    Less label-stable than :class:`EndpointMapper`: if the upstream API
    changes a path format, the label may shift. Prefer the mapper when
    you can.
    """

    # uuid: 8-4-4-4-12 hex with dashes (case-insensitive)
    _UUID_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    # plain hex >= 16 chars (object IDs, content hashes, ...)
    _HEX_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
    # pure decimal (any length)
    _NUM_RE = re.compile(r"^\d+$")
    # dashed-id heuristic: contains a dash AND a digit (e.g. abc-123-def)
    _DASHED_RE = re.compile(r"^(?=.*[A-Za-z0-9])(?=.*-)(?=.*\d)[A-Za-z0-9\-]+$")

    def __call__(self, path: str) -> str:
        # Keep leading slash semantics if present.
        leading_slash = path.startswith("/")
        trimmed = path.lstrip("/")
        if not trimmed:
            return path
        out_segments = [self._template_segment(s) for s in trimmed.split("/")]
        joined = "/".join(out_segments)
        return f"/{joined}" if leading_slash else joined

    @classmethod
    def _template_segment(cls, segment: str) -> str:
        if not segment:
            return segment
        if (
            cls._UUID_RE.match(segment)
            or cls._HEX_RE.match(segment)
            or cls._NUM_RE.match(segment)
            or cls._DASHED_RE.match(segment)
        ):
            return "{id}"
        return segment


__all__ = [
    "EndpointMapper",
    "PathTemplater",
    "record_upstream_http_request",
    "record_upstream_http_error",
    "upstream_http_requests",
    "upstream_http_errors",
    "upstream_http_duration",
]
