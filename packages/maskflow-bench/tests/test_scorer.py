from __future__ import annotations

import json
from pathlib import Path

import maskflow_pack_india  # noqa: F401 -- registers AADHAAR/PAN/etc. recognizers
from maskflow_bench.scorer import score_my_data


def test_score_my_data_runs_maskflow_end_to_end(tmp_path: Path) -> None:
    path = tmp_path / "my.jsonl"
    # Structurally valid (checksum-passing) but fabricated for this test --
    # not a real allotted PAN.
    row = {
        "text": "Please update my PAN ABCDE1234F on file.",
        "entities": [{"start": 22, "end": 32, "label": "PAN"}],
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    num_docs, labels, result = score_my_data(path)

    assert num_docs == 1
    assert labels == ("PAN",)
    assert result.name == "maskflow"
    assert result.available is True
    assert "PAN" in result.strict
    assert "PAN" in result.partial


def test_score_my_data_respects_limit(tmp_path: Path) -> None:
    path = tmp_path / "my.jsonl"
    rows = [{"text": f"doc {i}", "entities": []} for i in range(5)]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    num_docs, _labels, _result = score_my_data(path, limit=2)
    assert num_docs == 2
