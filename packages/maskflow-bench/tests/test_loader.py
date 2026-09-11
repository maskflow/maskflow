from __future__ import annotations

import json
from pathlib import Path

import pytest
from maskflow_bench.loader import LoaderError, load_my_data


def _write(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")


def test_minimal_line_needs_only_text_and_entities(tmp_path: Path) -> None:
    path = tmp_path / "my.jsonl"
    # PAN below is structurally shaped but not a real allotted number --
    # synthetic fixture data only.
    _write(
        path,
        [{"text": "PAN: ABCDE1234F", "entities": [{"start": 5, "end": 15, "label": "PAN"}]}],
    )
    docs = load_my_data(path)
    assert len(docs) == 1
    doc = docs[0]
    assert doc.gold == ((5, 15, "PAN"),)
    assert doc.decoys == ()
    # Defaults applied when the user's file doesn't supply them.
    assert doc.domain == "user_data"
    assert doc.lang == "en"
    assert doc.id == "line-1"


def test_explicit_id_domain_lang_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "my.jsonl"
    _write(
        path,
        [
            {
                "id": "ticket-42",
                "text": "x",
                "entities": [],
                "domain": "support_ticket",
                "lang": "en-hi",
            }
        ],
    )
    doc = load_my_data(path)[0]
    assert doc.id == "ticket-42"
    assert doc.domain == "support_ticket"
    assert doc.lang == "en-hi"


def test_hard_negative_value_class_goes_to_decoys(tmp_path: Path) -> None:
    path = tmp_path / "my.jsonl"
    _write(
        path,
        [
            {
                "text": "invoice INV-0001",
                "entities": [
                    {"start": 8, "end": 16, "label": "PAN_SHAPED", "value_class": "hard_negative"}
                ],
            }
        ],
    )
    doc = load_my_data(path)[0]
    assert doc.gold == ()
    assert doc.decoys == ((8, 16, "PAN_SHAPED"),)


def test_limit_takes_first_n_in_file_order(tmp_path: Path) -> None:
    path = tmp_path / "my.jsonl"
    _write(path, [{"text": f"t{i}", "entities": []} for i in range(5)])
    docs = load_my_data(path, limit=2)
    assert [d.text for d in docs] == ["t0", "t1"]


@pytest.mark.parametrize(
    "row",
    [
        {"entities": []},  # missing text
        {"text": "x"},  # missing entities
        {"text": "x", "entities": [{"start": 0, "end": 1}]},  # entity missing label
        {"text": "x", "entities": [{"start": 0, "label": "PAN"}]},  # entity missing end
        {"text": "x", "entities": "not-a-list"},
        {"text": 123, "entities": []},
        {"text": "x", "entities": [{"start": "0", "end": 1, "label": "PAN"}]},
    ],
)
def test_malformed_line_raises_loader_error_with_line_number(tmp_path: Path, row: dict) -> None:
    path = tmp_path / "my.jsonl"
    # Line 1 is valid, so the error must point at line 2, not line 1.
    _write(path, [{"text": "ok", "entities": []}])
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    with pytest.raises(LoaderError) as exc_info:
        load_my_data(path)
    assert exc_info.value.line_no == 2


def test_invalid_json_raises_loader_error(tmp_path: Path) -> None:
    path = tmp_path / "my.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(LoaderError) as exc_info:
        load_my_data(path)
    assert exc_info.value.line_no == 1
