"""Best-effort attribution: pull provider / service / timestamp / role out
of a decoded row using the spec's *_field selectors, tolerating whatever
shape the row actually has."""

from __future__ import annotations

from datetime import datetime, timezone

from ..fieldsel import first_str
from ..spec import SourceSpec


def parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    # ISO 8601 (the common case for JSON logs), tolerating a trailing Z.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    # Unix epoch seconds or milliseconds.
    try:
        num = float(value)
    except ValueError:
        return None
    if num > 1e11:  # milliseconds
        num /= 1000.0
    try:
        return datetime.fromtimestamp(num, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def row_metadata(
    row: object, spec: SourceSpec
) -> tuple[str | None, str | None, datetime | None, str | None]:
    provider = first_str(row, spec.provider_field) or spec.provider
    service = first_str(row, spec.service_field)
    timestamp = parse_timestamp(first_str(row, spec.timestamp_field))
    role = first_str(row, spec.role_field)
    return provider, service, timestamp, role
