"""dir source: recurse a directory, scan every recognised file
(.jsonl/.ndjson/.json as line-delimited JSON, .csv, .txt/.log as raw
lines). Files are visited in sorted relative-path order so a resumed run
is deterministic; the cursor is "<relpath>\x1f<inner>"."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from ..fieldsel import FieldSelector, extract_all
from ..spec import SourceSpec
from ._files import (
    CSV_EXTENSIONS,
    JSONL_EXTENSIONS,
    TEXT_EXTENSIONS,
    cursor_of,
    iter_csv_rows,
    iter_json_lines,
    iter_text_lines,
    record_id,
)
from ._meta import row_metadata
from .base import Preflight, ScanRecord, Source, SourceConfigError, SourceEstimate

_SEP = "\x1f"
_JSON_EXT = (*JSONL_EXTENSIONS, ".json")
_RECOGNISED = (*_JSON_EXT, *CSV_EXTENSIONS, *TEXT_EXTENSIONS)


class DirSource:
    name: ClassVar[str] = "dir"

    def __init__(self, root: Path, selectors: tuple[FieldSelector, ...], spec: SourceSpec) -> None:
        self._root = root
        self._selectors = selectors
        self._columns = tuple(
            c.strip() for spec_c in spec.columns for c in spec_c.split(",") if c.strip()
        )
        self._spec = spec

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        root = Path(spec.target)
        if not root.is_dir():
            raise SourceConfigError(f"dir source: not a directory: {spec.target}")
        selectors = tuple(FieldSelector.parse(f) for f in spec.fields)
        if not selectors and not spec.columns:
            raise SourceConfigError(
                "dir source needs --field (for JSON files) and/or --columns (for CSV files)"
            )
        return cls(root, selectors, spec)

    def preflight(self) -> Preflight:
        if not self._root.is_dir():
            return Preflight(False, f"not a directory: {self._root}")
        if not any(self._files()):
            return Preflight(
                False,
                f"no .jsonl/.ndjson/.json/.csv/.txt/.log files under {self._root}",
            )
        return Preflight(True)

    def estimate(self) -> SourceEstimate:
        total = sum(f.stat().st_size for f in self._files())
        return SourceEstimate(total_bytes=total)

    def _files(self) -> Iterator[Path]:
        return iter(
            sorted(
                (p for p in self._root.rglob("*") if p.is_file() and p.suffix in _RECOGNISED),
                key=lambda p: p.relative_to(self._root).as_posix(),
            )
        )

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        resume_rel, resume_inner = _split_cursor(resume_cursor)
        for path in self._files():
            rel = path.relative_to(self._root).as_posix()
            if resume_rel is not None and rel < resume_rel:
                continue
            inner = resume_inner if rel == resume_rel else 0
            yield from self._scan_file(path, rel, inner)

    def _scan_file(self, path: Path, rel: str, inner: int) -> Iterator[ScanRecord]:
        if path.suffix in _JSON_EXT:
            with open(path, "rb") as fh:
                for line in iter_json_lines(fh, resume_offset=inner):
                    texts = extract_all(line.obj, self._selectors)
                    if not texts:
                        continue
                    provider, service, timestamp, role = row_metadata(line.obj, self._spec)
                    for sub, text in enumerate(texts):
                        yield ScanRecord(
                            id=record_id(f"{rel}{_SEP}{line.end_offset}", sub),
                            text=text,
                            provider=provider or self._spec.provider,
                            service=service,
                            timestamp=timestamp,
                            role=role,
                            record_ref=f"{rel}#L{line.lineno}" if line.lineno >= 0 else rel,
                        )
        elif path.suffix in CSV_EXTENSIONS:
            with open(path, encoding="utf-8", newline="") as fh:
                for row_index, row in iter_csv_rows(fh, resume_index=inner):
                    for sub, col in enumerate(self._columns):
                        text = row.get(col)
                        if not text:
                            continue
                        yield ScanRecord(
                            id=record_id(f"{rel}{_SEP}{row_index}", sub),
                            text=text,
                            provider=self._spec.provider,
                            record_ref=f"{rel}#row{row_index}:{col}",
                        )
        else:  # .txt / .log
            with open(path, "rb") as fh:
                for line in iter_text_lines(fh, resume_offset=inner):
                    assert isinstance(line.obj, str)
                    yield ScanRecord(
                        id=record_id(f"{rel}{_SEP}{line.end_offset}", 0),
                        text=line.obj,
                        provider=self._spec.provider,
                        record_ref=f"{rel}#L{line.lineno}" if line.lineno >= 0 else rel,
                    )

    def cursor_after(self, record: ScanRecord) -> str:
        return cursor_of(record.id)


def _split_cursor(cursor: str | None) -> tuple[str | None, int]:
    if not cursor:
        return None, 0
    rel, _, inner = cursor.rpartition(_SEP)
    return rel, int(inner)
