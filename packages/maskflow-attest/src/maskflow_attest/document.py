"""``AttestationDocument`` -- the dated claim: "this pack version scored
these numbers against this public corpus, on this date, reproducibly."

Deliberately corpus- and pack-agnostic: nothing here knows about IndiaPII
or ``maskflow-pack-india`` specifically. What corpus, what pack, what
numbers -- all just fields, supplied by the caller (``run.py``, today
pointed at ``bench/indiapii/data/indiapii-v1.0.jsonl``). This module never
signs anything; it only defines the exact bytes ``signing.py`` signs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from typing import Any, Final

SCHEMA_VERSION: Final = "1"

# RFC3339 UTC, second precision, always 'Z' -- matches maskflow_evidence's
# own timestamp convention (see maskflow_evidence.schema._TS_RE) so
# anything that already parses an evidence timestamp parses this one too.
_TS_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(_TS_FORMAT)


class AttestationDocumentError(ValueError):
    """Raised by :meth:`AttestationDocument.from_dict` on a malformed or
    drifted document -- never silently coerced, since a caller verifying an
    attestation needs to know the shape it got isn't the shape it expected."""


@dataclass(frozen=True)
class AttestationDocument:
    pack_name: str
    pack_version: str
    corpus_name: str
    corpus_version: str
    num_docs: int
    canonical_labels: tuple[str, ...]
    # {label: {"strict": {precision, recall, f1, tp, fp, fn}, "partial": {...}}}
    metrics: dict[str, dict[str, dict[str, float | int | None]]]
    methodology: str
    reproduction_command: str
    engine_version: str
    issued_at: str = ""
    valid_until: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.issued_at:
            object.__setattr__(self, "issued_at", _now_iso())
        if not self.valid_until:
            issued = datetime.strptime(self.issued_at, _TS_FORMAT).replace(tzinfo=timezone.utc)
            valid_until = (issued + timedelta(days=90)).strftime(_TS_FORMAT)
            object.__setattr__(self, "valid_until", valid_until)
        if not isinstance(self.canonical_labels, tuple):
            object.__setattr__(self, "canonical_labels", tuple(self.canonical_labels))

    def to_dict(self) -> dict[str, Any]:
        """An explicit field list, never ``dataclasses.asdict``/``__dict__``
        -- same reasoning as ``EvidenceEvent.to_dict``: a future stray
        attribute cannot ride along unnoticed into a signed payload."""
        return {
            "schema_version": self.schema_version,
            "pack_name": self.pack_name,
            "pack_version": self.pack_version,
            "corpus_name": self.corpus_name,
            "corpus_version": self.corpus_version,
            "num_docs": self.num_docs,
            "canonical_labels": list(self.canonical_labels),
            "metrics": self.metrics,
            "methodology": self.methodology,
            "reproduction_command": self.reproduction_command,
            "engine_version": self.engine_version,
            "issued_at": self.issued_at,
            "valid_until": self.valid_until,
        }

    def canonical_json(self) -> str:
        """The exact byte string ``signing.py`` signs and verifies --
        sorted keys, compact separators, so signer and verifier always hash
        the same bytes regardless of dict insertion order or whitespace."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttestationDocument:
        """Rebuilds a document from :meth:`to_dict` output. Unknown keys
        are rejected (a signed document with an extra field the signer
        never signed is a red flag, not something to silently drop)."""
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise AttestationDocumentError(f"unknown field(s): {sorted(unknown)}")
        payload = dict(data)
        if "canonical_labels" in payload:
            payload["canonical_labels"] = tuple(payload["canonical_labels"])
        try:
            return cls(**payload)
        except TypeError as exc:
            raise AttestationDocumentError(f"malformed attestation document: {exc}") from exc
