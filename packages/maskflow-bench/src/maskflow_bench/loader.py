"""Lenient JSONL loader for a user's own labelled data (`maskflow bench
--my-data <path>`, packages/maskflow-cli), as opposed to corpus.py's
strict parser for the bundled benchmark corpora.

A user checking "is it accurate on my documents?" has no reason to know
about `domain`/`lang`/`value_class` -- those are benchmark-corpus
bookkeeping, not concepts a newcomer's own labelled file would naturally
carry. Only `text` and `entities[].{start,end,label}` are required; every
other field gets a sensible default. The result is the exact same
`Document` dataclass corpus.py produces, so every downstream function
(labels.canonical_labels, matching.evaluate, runner.run_adapter,
report.write_report) is used unmodified.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .corpus import Document

_REQUIRED_ENTITY_FIELDS = ("start", "end", "label")


@dataclass
class LoaderError(Exception):
    """Raised on one malformed line, with the 1-based line number so the
    CLI can report exactly where a user's file needs fixing -- never a raw
    KeyError/TypeError/JSONDecodeError with no context."""

    line_no: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line_no}: {self.message}"


def _parse_line(line_no: int, line: str) -> Document:
    try:
        row = json.loads(line)
    except json.JSONDecodeError as e:
        raise LoaderError(line_no, f"invalid JSON ({e})") from e
    if not isinstance(row, dict):
        raise LoaderError(line_no, "each line must be a JSON object")

    if "text" not in row:
        raise LoaderError(line_no, "missing required field 'text'")
    text = row["text"]
    if not isinstance(text, str):
        raise LoaderError(line_no, "'text' must be a string")

    if "entities" not in row:
        raise LoaderError(line_no, "missing required field 'entities'")
    raw_entities = row["entities"]
    if not isinstance(raw_entities, list):
        raise LoaderError(line_no, "'entities' must be a list")

    gold = []
    decoys = []
    for i, entity in enumerate(raw_entities):
        if not isinstance(entity, dict):
            raise LoaderError(line_no, f"entities[{i}] must be an object")
        missing = [f for f in _REQUIRED_ENTITY_FIELDS if f not in entity]
        if missing:
            raise LoaderError(line_no, f"entities[{i}] missing field(s): {', '.join(missing)}")
        start, end, label = entity["start"], entity["end"], entity["label"]
        if not isinstance(start, int) or not isinstance(end, int):
            raise LoaderError(line_no, f"entities[{i}]: 'start'/'end' must be integers")
        if not isinstance(label, str):
            raise LoaderError(line_no, f"entities[{i}]: 'label' must be a string")
        span = (start, end, label)
        if entity.get("value_class", "positive") == "positive":
            gold.append(span)
        else:
            decoys.append(span)

    return Document(
        id=str(row.get("id", f"line-{line_no}")),
        text=text,
        domain=str(row.get("domain", "user_data")),
        lang=str(row.get("lang", "en")),
        gold=tuple(gold),
        decoys=tuple(decoys),
    )


def iter_my_data(path: Path) -> Iterator[Document]:
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if line:
                yield _parse_line(line_no, line)


def load_my_data(path: Path, limit: int | None = None) -> list[Document]:
    """Loads `path` in file order. `limit` scores only the first N lines --
    a quick smoke run on a large file, same convention as corpus.py's."""
    docs = []
    for i, doc in enumerate(iter_my_data(path)):
        if limit is not None and i >= limit:
            break
        docs.append(doc)
    return docs
