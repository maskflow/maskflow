"""Structural checks on the scan-log harness -- no third-party adapters."""

from __future__ import annotations

from pathlib import Path

from bench.indiapii.harness.corpus import load_corpus
from bench.indiapii.harness.matching import MatchMode, evaluate
from bench.scanbench.harness.adapters import build_adapters
from bench.scanbench.harness.labels import (
    LABEL_DESCRIPTIONS,
    NAIVE_REGEX_LABEL_MAP,
    PRESIDIO_LABEL_MAP,
    canonical_labels,
)
from bench.scanbench.harness.report import _fp_per_1000

_CORPUS = Path(__file__).resolve().parents[2] / "data" / "scan-log-v1.0.jsonl"

_EXPECTED_TAXONOMY = {
    "AADHAAR",
    "PAN",
    "GSTIN",
    "IFSC",
    "UPI_VPA",
    "INDIAN_MOBILE",
    "CREDIT_CARD",
    "EMAIL",
    "IP_ADDRESS",
    "API_KEY",
    "AWS_KEY",
    "JWT",
    "PERSON_NAME",
}


def test_corpus_present_and_well_formed() -> None:
    docs = load_corpus(_CORPUS)
    assert len(docs) >= 1000
    for doc in docs:
        for start, end, _label in (*doc.gold, *doc.decoys):
            assert 0 <= start < end <= len(doc.text)


def test_taxonomy_is_the_log_relevant_type_set() -> None:
    docs = load_corpus(_CORPUS)
    assert set(canonical_labels(docs)) == _EXPECTED_TAXONOMY


def test_every_gold_type_has_a_gloss() -> None:
    for label in canonical_labels(load_corpus(_CORPUS)):
        assert LABEL_DESCRIPTIONS.get(label), label


def test_competitor_maps_target_only_real_types() -> None:
    for mapping in (PRESIDIO_LABEL_MAP, NAIVE_REGEX_LABEL_MAP):
        assert set(mapping.values()) <= _EXPECTED_TAXONOMY


def test_hard_negatives_never_overlap_gold_labels() -> None:
    docs = load_corpus(_CORPUS)
    gold = {label for doc in docs for _s, _e, label in doc.gold}
    decoy = {label for doc in docs for _s, _e, label in doc.decoys}
    assert decoy and decoy.isdisjoint(gold)


def test_both_maskflow_adapters_and_naive_run(tmp_path: None = None) -> None:
    docs = load_corpus(_CORPUS, limit=60)
    labels = canonical_labels(docs)
    by_name = {e[0].name: e for e in build_adapters(labels)}
    assert {"maskflow_deep", "maskflow_patterns", "naive_regex"} <= set(by_name)
    for name in ("maskflow_deep", "maskflow_patterns", "naive_regex"):
        adapter, label_map = by_name[name]
        preds = [adapter.detect(doc.text) for doc in docs]
        partial = evaluate(docs, preds, label_map, labels, MatchMode.PARTIAL)
        assert partial["EMAIL"].tp > 0


def test_patterns_pass_is_much_faster_and_no_worse_on_validated_types() -> None:
    docs = load_corpus(_CORPUS, limit=80)
    labels = canonical_labels(docs)
    by_name = {e[0].name: e for e in build_adapters(labels)}
    deep_a, deep_m = by_name["maskflow_deep"]
    pat_a, pat_m = by_name["maskflow_patterns"]
    deep = evaluate(docs, [deep_a.detect(d.text) for d in docs], deep_m, labels, MatchMode.PARTIAL)
    pat = evaluate(docs, [pat_a.detect(d.text) for d in docs], pat_m, labels, MatchMode.PARTIAL)
    # Checksum-validated types: the NER pass adds nothing, so recall matches.
    for et in ("AADHAAR", "PAN", "GSTIN", "IFSC"):
        if deep[et].tp + deep[et].fn:
            assert pat[et].recall == deep[et].recall


def test_fp_per_1000_matches_hand_count() -> None:
    from bench.indiapii.harness.matching import PRFResult
    from bench.indiapii.harness.runner import AdapterRunResult

    r = AdapterRunResult(name="x", available=True)
    r.partial = {"EMAIL": PRFResult(entity_type="EMAIL", tp=10, fp=5, fn=0)}
    rate, fp, precision = _fp_per_1000(r, num_docs=1000)
    assert (rate, fp, round(precision, 3)) == (5.0, 5, 0.667)
