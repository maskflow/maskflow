"""Loads bench/indiapii/data/*.jsonl into Document objects.

Each corpus line has an `entities` list mixing `value_class: "positive"`
(real gold spans) and `value_class: "hard_negative"` (decoy spans, shaped
like real PII but never gold -- see generator/hard_negatives.py). Document
keeps these separate: `gold` is the only thing matching.py scores recall
against; `decoys` exist purely so a prediction landing on one still counts
as a false positive for whatever type it claimed (see matching.py).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    domain: str
    lang: str
    gold: tuple[tuple[int, int, str], ...]
    decoys: tuple[tuple[int, int, str], ...]

    @property
    def size_bytes(self) -> int:
        return len(self.text.encode("utf-8"))


def _parse_line(line: str) -> Document:
    row = json.loads(line)
    gold = []
    decoys = []
    for e in row["entities"]:
        span = (e["start"], e["end"], e["label"])
        if e["value_class"] == "positive":
            gold.append(span)
        else:
            decoys.append(span)
    return Document(
        id=row["id"],
        text=row["text"],
        domain=row["domain"],
        lang=row["lang"],
        gold=tuple(gold),
        decoys=tuple(decoys),
    )


def iter_corpus(path: Path) -> Iterator[Document]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield _parse_line(line)


def load_corpus(path: Path, limit: int | None = None) -> list[Document]:
    """Loads `path` in file order (the corpus's own doc-id order), which is
    already deterministic per-seed at generation time -- `limit` therefore
    always selects the same first-N documents run to run, which is what
    the CI regression subset (see harness/tests/test_ci_regression.py)
    relies on for a stable baseline.
    """
    docs = []
    for i, doc in enumerate(iter_corpus(path)):
        if limit is not None and i >= limit:
            break
        docs.append(doc)
    return docs
