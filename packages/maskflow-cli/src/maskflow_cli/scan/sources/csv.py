"""csv source: header-first CSV, --columns names the text columns. Resume
is by data-row index (CSV has no stable byte-offset story once quoting and
embedded newlines are in play)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from ..spec import SourceSpec
from ._files import cursor_of, iter_csv_rows, record_id, resolve_columns
from ._meta import row_metadata
from .base import Preflight, ScanRecord, Source, SourceConfigError, SourceEstimate


class CsvSource:
    name: ClassVar[str] = "csv"

    def __init__(self, path: str, columns: tuple[str, ...], spec: SourceSpec) -> None:
        self._path = path
        self._columns = columns
        self._spec = spec

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        if not Path(spec.target).is_file():
            raise SourceConfigError(f"csv source: no such file: {spec.target}")
        return cls(spec.target, resolve_columns(spec.columns), spec)

    def preflight(self) -> Preflight:
        p = Path(self._path)
        if not p.is_file():
            return Preflight(False, f"no such file: {self._path}")
        with p.open("r", encoding="utf-8", newline="") as fh:
            header = fh.readline()
        missing = [c for c in self._columns if c not in header]
        if missing:
            return Preflight(False, f"columns not in CSV header: {', '.join(missing)}")
        return Preflight(True)

    def estimate(self) -> SourceEstimate:
        return SourceEstimate(total_bytes=Path(self._path).stat().st_size)

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        resume_index = int(resume_cursor) if resume_cursor else 0
        with open(self._path, encoding="utf-8", newline="") as fh:
            for row_index, row in iter_csv_rows(fh, resume_index=resume_index):
                # A CSV row is a flat {header: value} dict, so the same
                # *_field selectors the JSON sources use resolve here as
                # plain column lookups.
                provider, service, timestamp, role = row_metadata(row, self._spec)
                for sub, col in enumerate(self._columns):
                    text = row.get(col)
                    if not text:
                        continue
                    yield ScanRecord(
                        id=record_id(str(row_index), sub),
                        text=text,
                        provider=provider or self._spec.provider,
                        service=service,
                        timestamp=timestamp,
                        role=role,
                        record_ref=f"{self._path}#row{row_index}:{col}",
                    )

    def cursor_after(self, record: ScanRecord) -> str:
        return cursor_of(record.id)
