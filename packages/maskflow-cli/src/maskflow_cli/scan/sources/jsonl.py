"""jsonl / ndjson source: one JSON object per line, --field selectors pick
the text that reached the provider. Streams by byte offset; resume seeks."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from ..fieldsel import FieldSelector, extract_all
from ..spec import SourceSpec
from ._files import cursor_of, iter_json_lines, record_id
from ._meta import row_metadata
from .base import (
    Preflight,
    ScanRecord,
    Source,
    SourceConfigError,
    SourceEstimate,
)


class JsonlSource:
    name: ClassVar[str] = "jsonl"

    def __init__(self, path: str, selectors: tuple[FieldSelector, ...], spec: SourceSpec) -> None:
        self._path = path
        self._selectors = selectors
        self._spec = spec
        self._is_stdin = path == "-"

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        if not spec.fields:
            raise SourceConfigError(
                "jsonl source needs at least one --field, e.g. --field messages[].content"
            )
        if spec.target != "-" and not Path(spec.target).is_file():
            raise SourceConfigError(f"jsonl source: no such file: {spec.target}")
        selectors = tuple(FieldSelector.parse(f) for f in spec.fields)
        return cls(spec.target, selectors, spec)

    def preflight(self) -> Preflight:
        if self._is_stdin:
            return Preflight(True)
        p = Path(self._path)
        if not p.is_file():
            return Preflight(False, f"no such file: {self._path}")
        try:
            p.open("rb").close()
        except OSError as exc:  # noqa: BLE001 -- message is the point
            return Preflight(False, f"cannot read {self._path}: {exc.strerror}")
        return Preflight(True)

    def estimate(self) -> SourceEstimate:
        if self._is_stdin:
            return SourceEstimate()
        return SourceEstimate(total_bytes=Path(self._path).stat().st_size)

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        resume_offset = int(resume_cursor) if resume_cursor else 0
        ref_name = "<stdin>" if self._is_stdin else self._path
        stream = sys.stdin.buffer if self._is_stdin else open(self._path, "rb")  # noqa: SIM115
        try:
            for line in iter_json_lines(stream, resume_offset=resume_offset):
                texts = extract_all(line.obj, self._selectors)
                if not texts:
                    continue
                provider, service, timestamp, role = row_metadata(line.obj, self._spec)
                loc = f"L{line.lineno}" if line.lineno >= 0 else f"@{line.end_offset}"
                for sub, text in enumerate(texts):
                    yield ScanRecord(
                        id=record_id(str(line.end_offset), sub),
                        text=text,
                        provider=provider,
                        service=service,
                        timestamp=timestamp,
                        role=role,
                        record_ref=f"{ref_name}#{loc}",
                    )
        finally:
            if not self._is_stdin:
                stream.close()

    def cursor_after(self, record: ScanRecord) -> str:
        return cursor_of(record.id)
