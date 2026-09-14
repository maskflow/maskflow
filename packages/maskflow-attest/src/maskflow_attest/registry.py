"""``AttestationRegistry`` -- an append-only, JSON-lines record of every
attestation issued, with revocation.

Deliberately dumb: this is a local file format plus a thin Python API, not
a service. A hosted registry endpoint (``GET /attestations/:pack_version``,
public, unauthenticated) can mirror this same format -- this module is
what such an endpoint would wrap, not a stub waiting to be replaced by it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .document import AttestationDocument


@dataclass(frozen=True)
class AttestationRecord:
    document: AttestationDocument
    signature: str
    # Informational only -- bookkeeping for key rotation ("which of our
    # keys signed this"), never itself the trust anchor. See signing.py's
    # module docstring: verification always uses a caller-supplied,
    # out-of-band trusted key, never this field.
    signer_public_key: str
    revoked: bool = False
    revoked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "signature": self.signature,
            "signer_public_key": self.signer_public_key,
            "revoked": self.revoked,
            "revoked_reason": self.revoked_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttestationRecord:
        return cls(
            document=AttestationDocument.from_dict(data["document"]),
            signature=data["signature"],
            signer_public_key=data["signer_public_key"],
            revoked=bool(data.get("revoked", False)),
            revoked_reason=str(data.get("revoked_reason", "")),
        )


class AttestationRegistry:
    """One JSON-lines file, one :class:`AttestationRecord` per line.
    Effectively append-only: :meth:`revoke` is the only operation that
    rewrites an existing entry, and even then only flips ``revoked`` --
    the record and its original signature are never deleted, so a
    previously-downloaded copy of a since-revoked attestation still
    verifies (revocation is a correction layered on top, not an erasure)."""

    def __init__(self, records: list[AttestationRecord] | None = None) -> None:
        self._records: list[AttestationRecord] = list(records) if records else []

    @property
    def records(self) -> tuple[AttestationRecord, ...]:
        return tuple(self._records)

    def add(self, record: AttestationRecord) -> None:
        self._records.append(record)

    def latest(self, pack_name: str, pack_version: str | None = None) -> AttestationRecord | None:
        """The most recently issued, non-revoked record for ``pack_name``
        (optionally pinned to ``pack_version``). ``None`` if nothing
        matches -- never raises, since "no attestation yet" is an expected,
        checkable state, not an error."""
        candidates = [
            r
            for r in self._records
            if r.document.pack_name == pack_name
            and (pack_version is None or r.document.pack_version == pack_version)
            and not r.revoked
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.document.issued_at)

    def revoke(self, pack_name: str, pack_version: str, *, reason: str) -> int:
        """Marks every matching, not-already-revoked record revoked.
        Returns the count changed (0 if nothing matched)."""
        changed = 0
        updated: list[AttestationRecord] = []
        for r in self._records:
            matches = r.document.pack_name == pack_name and r.document.pack_version == pack_version
            if matches and not r.revoked:
                updated.append(
                    AttestationRecord(
                        document=r.document,
                        signature=r.signature,
                        signer_public_key=r.signer_public_key,
                        revoked=True,
                        revoked_reason=reason,
                    )
                )
                changed += 1
            else:
                updated.append(r)
        self._records = updated
        return changed

    @classmethod
    def load(cls, path: Path) -> AttestationRegistry:
        if not path.exists():
            return cls()
        records = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(AttestationRecord.from_dict(json.loads(line)))
        return cls(records)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for r in self._records:
                f.write(json.dumps(r.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")
