from __future__ import annotations

from pathlib import Path

from bench.indiapii.harness.corpus import Document
from bench.indiapii.quality.tasks import (
    EXTRACT_FIELD_SCHEMAS,
    TASK_TYPE_COUNTS,
    build_tasks,
    load_tasks,
    write_tasks,
)


def _doc(doc_id: str, domain: str, text: str, gold: tuple) -> Document:
    return Document(id=doc_id, text=text, domain=domain, lang="en", gold=gold, decoys=())


def _kyc_doc(doc_id: str) -> Document:
    text = "Name: Priya Iyer, Aadhaar: 234567890124, PAN: ABCDE1234F, Mobile: 9876543210"
    gold = (
        (6, 16, "PERSON_NAME"),
        (27, 39, "AADHAAR"),
        (46, 56, "PAN"),
        (66, 76, "INDIAN_MOBILE"),
    )
    return _doc(doc_id, "kyc_form", text, gold)


class TestBuildTasks:
    def test_counts_match_task_type_counts(self) -> None:
        docs = [_kyc_doc(f"doc-{i:03d}") for i in range(300)]
        tasks = build_tasks(docs, seed=1)
        counts: dict[str, int] = {}
        for t in tasks:
            counts[t.task_type] = counts.get(t.task_type, 0) + 1
        assert counts == TASK_TYPE_COUNTS
        assert len(tasks) == sum(TASK_TYPE_COUNTS.values())

    def test_deterministic_for_same_seed(self) -> None:
        docs = [_kyc_doc(f"doc-{i:03d}") for i in range(300)]
        first = build_tasks(docs, seed=42)
        second = build_tasks(docs, seed=42)
        assert [t.to_json() for t in first] == [t.to_json() for t in second]

    def test_extract_fields_restricted_to_schema_domains(self) -> None:
        non_schema_docs = [_doc(f"other-{i}", "some_unknown_domain", "text", ()) for i in range(10)]
        kyc_docs = [_kyc_doc(f"kyc-{i:03d}") for i in range(80)]
        tasks = build_tasks(non_schema_docs + kyc_docs, seed=1)
        extract_tasks = [t for t in tasks if t.task_type == "extract_fields"]
        assert extract_tasks  # some were produced
        assert all(t.domain in EXTRACT_FIELD_SCHEMAS for t in extract_tasks)

    def test_gold_fields_extracted_from_document(self) -> None:
        docs = [_kyc_doc(f"doc-{i:03d}") for i in range(80)]
        tasks = build_tasks(docs, seed=1)
        extract_task = next(t for t in tasks if t.task_type == "extract_fields")
        assert extract_task.gold_fields == {
            "applicant_name": "Priya Iyer",
            "aadhaar": "234567890124",
            "pan": "ABCDE1234F",
            "mobile": "9876543210",
            "address": None,
            "pin_code": None,
        }

    def test_summarize_and_draft_reply_have_no_gold_fields(self) -> None:
        docs = [_kyc_doc(f"doc-{i:03d}") for i in range(300)]
        tasks = build_tasks(docs, seed=1)
        for t in tasks:
            if t.task_type != "extract_fields":
                assert t.gold_fields == {}


def test_write_then_load_round_trips(tmp_path: Path) -> None:
    docs = [_kyc_doc(f"doc-{i:03d}") for i in range(300)]
    tasks = build_tasks(docs, seed=7)
    out = tmp_path / "quality.jsonl"
    write_tasks(tasks, out)
    loaded = load_tasks(out)
    assert [t.to_json() for t in loaded] == [t.to_json() for t in tasks]


def test_task_ids_are_unique() -> None:
    docs = [_kyc_doc(f"doc-{i:03d}") for i in range(300)]
    tasks = build_tasks(docs, seed=1)
    ids = [t.id for t in tasks]
    assert len(ids) == len(set(ids))
