from __future__ import annotations

import json

import pytest
from maskflow_attest.document import AttestationDocument, AttestationDocumentError


def _doc(**over: object) -> AttestationDocument:
    base: dict[str, object] = dict(
        pack_name="maskflow-pack-india",
        pack_version="0.5.1",
        corpus_name="indiapii-v1.0",
        corpus_version="1.0",
        num_docs=100,
        canonical_labels=("PAN", "EMAIL"),
        metrics={
            "PAN": {
                "strict": {"precision": 1.0, "recall": 0.9, "f1": 0.947, "tp": 9, "fp": 0, "fn": 1}
            }
        },
        methodology="test",
        reproduction_command="maskflow-attest run ...",
        engine_version="0.8.0",
    )
    base.update(over)
    return AttestationDocument(**base)  # type: ignore[arg-type]


def test_issued_at_and_valid_until_default_to_90_days_apart() -> None:
    doc = _doc()
    assert doc.issued_at
    assert doc.valid_until > doc.issued_at


def test_explicit_issued_at_is_kept() -> None:
    doc = _doc(issued_at="2026-01-01T00:00:00Z", valid_until="2026-02-01T00:00:00Z")
    assert doc.issued_at == "2026-01-01T00:00:00Z"
    assert doc.valid_until == "2026-02-01T00:00:00Z"


def test_canonical_labels_coerced_to_tuple() -> None:
    doc = _doc(canonical_labels=["PAN", "EMAIL"])
    assert doc.canonical_labels == ("PAN", "EMAIL")


def test_to_dict_from_dict_round_trip() -> None:
    doc = _doc()
    restored = AttestationDocument.from_dict(doc.to_dict())
    assert restored == doc


def test_canonical_json_is_sorted_and_stable() -> None:
    doc = _doc()
    first = doc.canonical_json()
    second = doc.canonical_json()
    assert first == second
    parsed = json.loads(first)
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_from_dict_rejects_unknown_field() -> None:
    data = _doc().to_dict()
    data["extra_field"] = "surprise"
    with pytest.raises(AttestationDocumentError, match="unknown field"):
        AttestationDocument.from_dict(data)


def test_from_dict_rejects_malformed_data() -> None:
    with pytest.raises(AttestationDocumentError):
        AttestationDocument.from_dict({"pack_name": "x"})
