"""``EvidenceEvent`` -- the one record type the evidence layer emits.

Every downstream guarantee in R5 rests on a single property: **no field of
this event can carry free text.** It is enforced structurally here (every
field is a slug, a bounded number, an enum-like literal, or a generated
identifier -- there is no `str` field a caller fills in freely), and again
in CI by ``tests/test_schema_metadata_only.py`` and ``guard.py``.

The event describes *what was masked* -- an entity type, a count, the
recognizer that fired, the action taken -- and the context it happened in
(service, environment, provider, model, versions). It never contains the
detected value, the placeholder it became, or the mapping between them.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any, Final

# The four things that can happen to a detected span. Mirrors
# maskflow_core.Strategy plus "passed" (detected but left in place -- below
# threshold or excluded by config).
ACTIONS: Final = ("masked", "redacted", "surrogate", "passed")

# A slug: what every human-or-machine-named field is restricted to. Starts
# alphanumeric, then a bounded run of a tiny safe alphabet. One ':' is
# allowed anywhere after the first char so recognizer ids ("pattern:AADHAAR",
# "ner:PERSON") fit. 64 chars is well past any real service/model/pack name
# and short enough that it cannot smuggle a sentence.
_SLUG_RE: Final = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._+:-]{0,63})$")

# RFC3339 UTC, second precision, always 'Z' -- the exact shape _now_iso()
# produces. Validated on the way back in (from_dict) so a hand-built event
# cannot carry a free-text timestamp.
_TS_RE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# 32 lowercase hex chars -- uuid4().hex.
_EVENT_ID_RE: Final = re.compile(r"^[0-9a-f]{32}$")

# session_id is caller-supplied and opaque by contract (a hash or a uuid,
# never a username/email). We still bound it hard: hex/uuid/base32-ish only,
# 8..128 chars. A caller that puts an email here fails construction.
_SESSION_ID_RE: Final = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

# PEP 440-ish: what importlib.metadata.version() returns for our packages,
# plus the literal "none"/"unknown" fallbacks versions.py may produce.
_VERSION_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


class EvidenceSchemaError(ValueError):
    """A field failed validation. Carries the field name and the reason --
    never the offending value (CLAUDE.md rule 1)."""

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"evidence field {field_name!r}: {reason}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(field_name: str, value: Any, pattern: re.Pattern[str]) -> None:
    if not isinstance(value, str) or not pattern.match(value):
        raise EvidenceSchemaError(field_name, "not a valid slug/identifier for this field")


@dataclass(frozen=True)
class EvidenceEvent:
    """One masking decision, aggregated by (entity_type, recognizer, action).

    Construct via :func:`maskflow_evidence.derive` helpers, not by hand, in
    normal use. Every field is validated in ``__post_init__``; a value that
    is not a bounded slug/number/known-literal raises ``EvidenceSchemaError``.
    """

    # --- what was masked --------------------------------------------------
    entity_type: str
    count: int
    score: float
    recognizer: str
    action: str

    # --- where it happened ----------------------------------------------
    service: str
    environment: str
    session_id: str
    pack_version: str
    engine_version: str
    provider: str | None = None
    model: str | None = None

    # --- generated -----------------------------------------------------
    event_id: str = ""
    ts: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", self.event_id or uuid.uuid4().hex)
        object.__setattr__(self, "ts", self.ts or _now_iso())

        _check("event_id", self.event_id, _EVENT_ID_RE)
        _check("ts", self.ts, _TS_RE)
        _check("session_id", self.session_id, _SESSION_ID_RE)
        _check("entity_type", self.entity_type, _SLUG_RE)
        _check("recognizer", self.recognizer, _SLUG_RE)
        _check("service", self.service, _SLUG_RE)
        _check("environment", self.environment, _SLUG_RE)
        _check("pack_version", self.pack_version, _VERSION_RE)
        _check("engine_version", self.engine_version, _VERSION_RE)

        if self.provider is not None:
            _check("provider", self.provider, _SLUG_RE)
        if self.model is not None:
            _check("model", self.model, _SLUG_RE)

        if self.action not in ACTIONS:
            raise EvidenceSchemaError("action", f"must be one of {ACTIONS}")

        if not isinstance(self.count, int) or isinstance(self.count, bool) or self.count < 1:
            raise EvidenceSchemaError("count", "must be an int >= 1")

        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not 0.0 <= float(self.score) <= 1.0
        ):
            raise EvidenceSchemaError("score", "must be a number in [0.0, 1.0]")
        object.__setattr__(self, "score", round(float(self.score), 4))

    def to_dict(self) -> dict[str, Any]:
        """The event as a plain dict, built from an explicit field list --
        never ``dataclasses.asdict`` / ``__dict__`` -- so a future stray
        attribute cannot ride along into an emitter."""
        return {
            "event_id": self.event_id,
            "ts": self.ts,
            "session_id": self.session_id,
            "service": self.service,
            "environment": self.environment,
            "entity_type": self.entity_type,
            "count": self.count,
            "score": self.score,
            "recognizer": self.recognizer,
            "action": self.action,
            "provider": self.provider,
            "model": self.model,
            "pack_version": self.pack_version,
            "engine_version": self.engine_version,
        }

    def to_json(self) -> str:
        """One compact JSON line. Runs the serialized form through the
        metadata-only guard as a last line of defence before it leaves the
        process -- see ``guard.assert_no_pii``."""
        from .guard import assert_no_pii

        line = json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        assert_no_pii(line)
        return line

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceEvent:
        """Rebuild an event from :meth:`to_dict` output, re-running every
        validator. Unknown keys are rejected."""
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise EvidenceSchemaError(next(iter(sorted(unknown))), "unknown field")
        return cls(**{k: v for k, v in data.items() if k in known})
