"""The Source adapter protocol and its shared types.

Every source -- a raw JSONL dump, an observability vendor's API, a Postgres
log table -- implements `Source` so `pipeline.py` can drive them all the
same way: preflight once, then stream `ScanRecord`s in a stable order,
resumable from an opaque cursor.

CLAUDE.md rule 1: `ScanRecord.text` is the only field detection runs on and
is repr-excluded; the error types below carry provider names / offsets /
counts only, never a payload.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from ..errors import SourceAuthError, SourceConfigError, SourceError

if TYPE_CHECKING:
    from ..spec import SourceSpec

__all__ = [
    "Source",
    "ScanRecord",
    "Preflight",
    "SourceEstimate",
    "SourceError",
    "SourceConfigError",
    "SourceAuthError",
]


@dataclass(frozen=True)
class ScanRecord:
    """One unit of text that (potentially) reached an LLM provider, with the
    metadata we can attribute it by. All metadata is best-effort: a raw
    JSONL dump may carry none of it."""

    # Stable, source-local identifier -- drives the deterministic NER sample
    # and dedup. e.g. "<relpath>#L42", a langfuse observation id, a pg pk.
    id: str
    # repr=False: raw text must never surface via a default repr, a debug
    # log line, or an unhandled traceback frame (CLAUDE.md rule 1).
    text: str = field(repr=False)
    provider: str | None = None
    service: str | None = None
    timestamp: datetime | None = None
    role: str | None = None
    # Human-readable path back to the originating row, PII-safe by
    # construction (a path + line, an id) -- shown in the report's excerpts.
    record_ref: str | None = None


@dataclass(frozen=True)
class Preflight:
    ok: bool
    reason: str = ""  # fix-it phrased; empty when ok


@dataclass(frozen=True)
class SourceEstimate:
    """Cheap size hints for the progress bar / ETA. Either or both may be
    None when the source genuinely cannot know without doing the work."""

    total_bytes: int | None = None
    total_records: int | None = None


@runtime_checkable
class Source(Protocol):
    name: ClassVar[str]

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        """Build from a parsed CLI spec. Reads credentials from the
        environment here, not from argv. Raises SourceConfigError with a
        fix-it message on bad config -- never a traceback."""
        ...

    def preflight(self) -> Preflight:
        """Cheap auth / connectivity / permission check, run once before the
        streaming loop starts."""
        ...

    def estimate(self) -> SourceEstimate:
        """Cheap size hint (file size, SELECT count(*), x-total-count
        header). May return SourceEstimate() (all-None)."""
        ...

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        """Lazily yield records in a STABLE order. When `resume_cursor` is
        given, fast-forward past the already-processed prefix (seek to a
        byte offset, WHERE key > :cur, replay to an API page cursor). Must
        stream: no whole-file read, no unbounded buffering, a server-side
        cursor for SQL."""
        ...

    def cursor_after(self, record: ScanRecord) -> str:
        """The opaque token that, passed back as `resume_cursor`, resumes
        immediately after `record`. Written into the checkpoint file after
        each committed batch."""
        ...
