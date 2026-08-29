from __future__ import annotations

import json
from pathlib import Path

from bench.indiapii.harness.corpus import load_corpus


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_load_corpus_splits_positive_and_hard_negative(tmp_path: Path) -> None:
    row = {
        "id": "doc-1",
        "text": "PAN: ABCDE1234F, invoice INV-0001",
        "entities": [
            {"start": 5, "end": 15, "label": "PAN", "value_class": "positive"},
            {
                "start": 25,
                "end": 33,
                "label": "PAN_SHAPED_INVOICE_NO",
                "value_class": "hard_negative",
            },
        ],
        "domain": "kyc_form",
        "lang": "en",
    }
    path = tmp_path / "corpus.jsonl"
    _write_jsonl(path, [row])

    docs = load_corpus(path)
    assert len(docs) == 1
    doc = docs[0]
    assert doc.gold == ((5, 15, "PAN"),)
    assert doc.decoys == ((25, 33, "PAN_SHAPED_INVOICE_NO"),)
    assert doc.size_bytes == len(doc.text.encode("utf-8"))


def test_load_corpus_limit_takes_first_n_in_file_order(tmp_path: Path) -> None:
    rows = [
        {"id": f"doc-{i}", "text": "t", "entities": [], "domain": "d", "lang": "en"}
        for i in range(5)
    ]
    path = tmp_path / "corpus.jsonl"
    _write_jsonl(path, rows)

    docs = load_corpus(path, limit=2)
    assert [d.id for d in docs] == ["doc-0", "doc-1"]
