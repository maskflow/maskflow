"""SourceSpec: the parsed, source-agnostic description of *what to scan*,
built from the CLI args and handed to `Source.from_spec()`.

Also owns `spec_fingerprint()` / `config_fingerprint()` -- the hashes the
checkpoint file uses to refuse resuming a run whose inputs or detection
config changed underneath it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SourceSpec:
    """Everything `Source.from_spec` needs. Credentials are NOT here -- a
    source reads those from the environment itself, so this object is safe
    to hash into the checkpoint and safe to log."""

    kind: str  # "jsonl" | "csv" | "dir" | "s3" | "postgres" | "langfuse" | ...
    target: str  # path, s3:// uri, connection string, or "" for API sources
    fields: tuple[str, ...] = ()  # --field selectors (jsonl/dir)
    columns: tuple[str, ...] = ()  # --columns (csv/dir)
    query: str | None = None  # --query (postgres)
    provider: str | None = None  # --provider constant
    provider_field: str | None = None
    service_field: str | None = None
    timestamp_field: str | None = None
    role_field: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    # Free-form per-source knobs that don't deserve a first-class field
    # (pg --key-column, api --project). Kept sorted when fingerprinting.
    extra: dict[str, str] = field(default_factory=dict)

    def fingerprint(self) -> str:
        payload = {
            "kind": self.kind,
            "target": self.target,
            "fields": list(self.fields),
            "columns": list(self.columns),
            "query": self.query,
            "provider": self.provider,
            "provider_field": self.provider_field,
            "service_field": self.service_field,
            "timestamp_field": self.timestamp_field,
            "role_field": self.role_field,
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
            "extra": dict(sorted(self.extra.items())),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class DetectionSpec:
    """The detection-affecting knobs, hashed separately from SourceSpec so a
    resumed run can tell "you changed --deep / your .maskflowrc" apart from
    "you changed the input"."""

    deep: bool
    config_fingerprint: str  # from the resolved .maskflowrc (see cmd.py)
    core_version: str

    def fingerprint(self) -> str:
        blob = f"{self.deep}|{self.config_fingerprint}|{self.core_version}"
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
