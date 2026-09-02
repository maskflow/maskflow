"""ScanSummary -> JSON. The same data the HTML renders from, for
programmatic diffing and dashboards."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime

from .summary import ScanSummary


def _default(obj: object) -> object:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"not JSON-serialisable: {type(obj)!r}")


def render_json(summary: ScanSummary) -> str:
    return json.dumps(dataclasses.asdict(summary), default=_default, indent=2) + "\n"
