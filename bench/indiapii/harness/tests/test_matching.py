from __future__ import annotations

from bench.indiapii.harness.corpus import Document
from bench.indiapii.harness.matching import MatchMode, evaluate


def _doc(gold: tuple, decoys: tuple = ()) -> Document:
    return Document(id="d1", text="x" * 100, domain="test", lang="en", gold=gold, decoys=decoys)


def test_strict_exact_match_is_tp() -> None:
    docs = [_doc(gold=((0, 5, "PAN"),))]
    preds = [[(0, 5, "PAN")]]
    r = evaluate(docs, preds, {"PAN": "PAN"}, ("PAN",), MatchMode.STRICT)
    assert r["PAN"].tp == 1
    assert r["PAN"].fp == 0
    assert r["PAN"].fn == 0


def test_strict_offset_mismatch_is_fn_and_fp() -> None:
    docs = [_doc(gold=((0, 5, "PAN"),))]
    preds = [[(0, 6, "PAN")]]  # one char off
    r = evaluate(docs, preds, {"PAN": "PAN"}, ("PAN",), MatchMode.STRICT)
    assert r["PAN"].tp == 0
    assert r["PAN"].fn == 1
    assert r["PAN"].fp == 1


def test_partial_overlap_counts_as_tp() -> None:
    docs = [_doc(gold=((10, 20, "AADHAAR"),))]
    preds = [[(12, 18, "AADHAAR")]]  # contained, not exact
    r = evaluate(docs, preds, {"AADHAAR": "AADHAAR"}, ("AADHAAR",), MatchMode.PARTIAL)
    assert r["AADHAAR"].tp == 1
    assert r["AADHAAR"].fp == 0
    assert r["AADHAAR"].fn == 0


def test_no_overlap_is_fn_and_fp() -> None:
    docs = [_doc(gold=((10, 20, "AADHAAR"),))]
    preds = [[(30, 40, "AADHAAR")]]
    r = evaluate(docs, preds, {"AADHAAR": "AADHAAR"}, ("AADHAAR",), MatchMode.PARTIAL)
    assert r["AADHAAR"].tp == 0
    assert r["AADHAAR"].fn == 1
    assert r["AADHAAR"].fp == 1


def test_hard_negative_hit_counts_as_false_positive() -> None:
    # A prediction landing on a hard-negative decoy span (never gold) is
    # still a false positive for whatever canonical type it claimed.
    docs = [_doc(gold=(), decoys=((0, 10, "PAN_SHAPED_INVOICE_NO"),))]
    preds = [[(0, 10, "PAN")]]
    r = evaluate(docs, preds, {"PAN": "PAN"}, ("PAN",), MatchMode.PARTIAL)
    assert r["PAN"].tp == 0
    assert r["PAN"].fp == 1
    assert r["PAN"].fn == 0


def test_unmapped_raw_label_is_dropped_not_scored() -> None:
    # An adapter's raw label with no entry in label_map (e.g. Presidio's
    # ORGANIZATION) must never count as a false positive against an
    # unrelated canonical type.
    docs = [_doc(gold=((0, 5, "PAN"),))]
    preds = [[(50, 60, "ORGANIZATION")]]
    r = evaluate(docs, preds, {"PAN": "PAN"}, ("PAN",), MatchMode.STRICT)
    assert r["PAN"].tp == 0
    assert r["PAN"].fp == 0
    assert r["PAN"].fn == 1


def test_precision_recall_f1_none_when_no_denominator() -> None:
    docs = [_doc(gold=())]
    preds = [[]]
    r = evaluate(docs, preds, {}, ("PAN",), MatchMode.STRICT)
    assert r["PAN"].precision is None
    assert r["PAN"].recall is None
    assert r["PAN"].f1 is None


def test_multiple_gold_spans_claim_distinct_predictions() -> None:
    # Two gold spans of the same type must each match a different
    # prediction, not both greedily match the first candidate.
    docs = [_doc(gold=((0, 5, "PAN"), (10, 15, "PAN")))]
    preds = [[(0, 5, "PAN"), (10, 15, "PAN")]]
    r = evaluate(docs, preds, {"PAN": "PAN"}, ("PAN",), MatchMode.STRICT)
    assert r["PAN"].tp == 2
    assert r["PAN"].fp == 0
    assert r["PAN"].fn == 0
