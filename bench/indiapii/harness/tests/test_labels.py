from __future__ import annotations

from bench.indiapii.harness.corpus import Document
from bench.indiapii.harness.labels import canonical_labels, identity_map


def test_canonical_labels_derived_from_gold_only() -> None:
    docs = [
        Document(
            id="d1",
            text="x",
            domain="t",
            lang="en",
            gold=((0, 1, "PAN"), (2, 3, "AADHAAR")),
            decoys=((4, 5, "PAN_SHAPED_INVOICE_NO"),),
        )
    ]
    labels = canonical_labels(docs)
    assert labels == ("AADHAAR", "PAN")
    assert "PAN_SHAPED_INVOICE_NO" not in labels


def test_identity_map_is_reflexive() -> None:
    m = identity_map(("AADHAAR", "PAN"))
    assert m == {"AADHAAR": "AADHAAR", "PAN": "PAN"}
