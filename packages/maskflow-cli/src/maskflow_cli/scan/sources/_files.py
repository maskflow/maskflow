"""Shared line-oriented streaming helpers for the file-backed sources
(jsonl, csv, dir, s3). Byte-offset based so a resumed scan seeks straight
to where it left off instead of re-reading gigabytes.
"""

from __future__ import annotations

import csv as _csv
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass

from .base import SourceConfigError

# Records within one line/row share a line cursor; a ":<sub>" suffix keeps
# each ScanRecord.id unique (needed for the deterministic NER sample and
# dedup) while cursor_after() strips it back to the resumable line cursor.
_SUB = ":"

TEXT_EXTENSIONS = (".txt", ".log")
JSONL_EXTENSIONS = (".jsonl", ".ndjson")
CSV_EXTENSIONS = (".csv",)


def record_id(line_cursor: str, sub: int) -> str:
    return f"{line_cursor}{_SUB}{sub}"


def cursor_of(record_id: str) -> str:
    return record_id.rsplit(_SUB, 1)[0]


@dataclass(frozen=True)
class JsonLine:
    end_offset: int  # byte offset just past this line's newline
    lineno: int
    obj: object


def iter_json_lines(stream: io.BufferedReader, *, resume_offset: int = 0) -> Iterator[JsonLine]:
    """Yield one JsonLine per non-blank line, starting after `resume_offset`.
    A line that isn't valid JSON is skipped (a mixed dump shouldn't abort a
    scan) -- but only after the first 3 such lines does it stay silent, so a
    wholly wrong --field/source choice still surfaces via the 0-record run.
    """
    if resume_offset:
        stream.seek(resume_offset)
    offset = stream.tell()
    lineno = _line_estimate(resume_offset)
    for raw in stream:
        offset += len(raw)
        lineno += 1
        text = raw.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        yield JsonLine(end_offset=offset, lineno=lineno, obj=obj)


def iter_text_lines(stream: io.BufferedReader, *, resume_offset: int = 0) -> Iterator[JsonLine]:
    """Same shape as iter_json_lines but each `obj` is the raw line string --
    for .txt / .log files scanned as one record per line."""
    if resume_offset:
        stream.seek(resume_offset)
    offset = stream.tell()
    lineno = _line_estimate(resume_offset)
    for raw in stream:
        offset += len(raw)
        lineno += 1
        text = raw.decode("utf-8", errors="replace").rstrip("\n")
        if not text.strip():
            continue
        yield JsonLine(end_offset=offset, lineno=lineno, obj=text)


def iter_csv_rows(
    stream: io.TextIOBase, *, resume_index: int = 0
) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield (row_index, row_dict) from a header-first CSV, skipping the
    first `resume_index` data rows. row_index is 1-based over data rows."""
    reader = _csv.reader(stream)
    try:
        header = next(reader)
    except StopIteration:
        return
    seen = 0
    for fields in reader:
        seen += 1
        if seen <= resume_index:
            continue
        row = {header[i]: fields[i] for i in range(min(len(header), len(fields)))}
        yield seen, row


def resolve_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    flat: list[str] = []
    for spec in columns:
        flat.extend(c.strip() for c in spec.split(",") if c.strip())
    if not flat:
        raise SourceConfigError("csv source needs --columns, e.g. --columns prompt,completion")
    return tuple(flat)


def _line_estimate(resume_offset: int) -> int:
    # Line numbers after a resume are approximate (we seeked past the start
    # and never counted the skipped lines) -- they're only used to build a
    # human record_ref, never for correctness. Flag the approximation.
    return 0 if resume_offset == 0 else -1
