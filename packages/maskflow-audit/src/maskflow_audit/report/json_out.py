"""AuditSummary -> audit.json.

The same data the HTML will render from, for programmatic diffing, the
`--ci` baseline, and the evidence product. Deterministic: given the same
tree and seed the only field that moves is `scope.generated_at`, which is
what lets a test assert byte-identical output across two runs.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime

from .summary import AuditSummary


def _default(obj: object) -> object:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"not JSON-serialisable: {type(obj)!r}")


def render_json(summary: AuditSummary) -> str:
    return json.dumps(dataclasses.asdict(summary), default=_default, indent=2) + "\n"
