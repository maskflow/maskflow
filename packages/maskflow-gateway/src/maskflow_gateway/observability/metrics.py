"""Prometheus metrics. Label sets are deliberately low-cardinality --
entity *type* (not value), route, provider, coarse status class, stage
name. No label ever carries a PII value or a session id.
"""

from __future__ import annotations

from collections.abc import Mapping

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()

DETECTIONS = Counter(
    "maskflow_detections_total",
    "PII spans detected, by entity type and direction (request = client->upstream, "
    "response = upstream->client).",
    ["entity_type", "direction"],
    registry=REGISTRY,
)

REQUESTS = Counter(
    "maskflow_requests_total",
    "Proxied requests, by route, provider and status class.",
    ["route", "provider", "status"],
    registry=REGISTRY,
)

ERRORS = Counter(
    "maskflow_errors_total",
    "Errors, by provider and error type.",
    ["provider", "type"],
    registry=REGISTRY,
)

STAGE_LATENCY = Histogram(
    "maskflow_stage_latency_seconds",
    "Per-stage latency: mask (request), upstream (provider round trip), unmask (response).",
    ["stage"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
    registry=REGISTRY,
)

ACTIVE_SESSIONS = Gauge(
    "maskflow_active_sessions",
    "Sessions currently held in the in-process cache (not the Redis total).",
    registry=REGISTRY,
)


def record_detections(counts: Mapping[str, int], direction: str) -> None:
    for entity_type, n in counts.items():
        if n:
            DETECTIONS.labels(entity_type=entity_type, direction=direction).inc(n)


def status_class(code: int) -> str:
    return f"{code // 100}xx"


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
