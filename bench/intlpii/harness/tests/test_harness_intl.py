"""Structural checks on the intl harness wiring -- no third-party adapter
deps, no network. Fast; runs on every CI leg that touches bench/.
"""

from __future__ import annotations

from pathlib import Path

from maskflow_bench.corpus import load_corpus
from maskflow_bench.matching import MatchMode, evaluate

from bench.intlpii.harness.adapters import build_adapters
from bench.intlpii.harness.labels import (
    LABEL_DESCRIPTIONS,
    MASK_PRIVACY_LABEL_MAP,
    PRESIDIO_LABEL_MAP,
    canonical_labels,
)

_CORPUS = Path(__file__).resolve().parents[2] / "data" / "intl-pii-v1.0.jsonl"

# The 12 types maskflow-pack-intl registers (see its __init__.py).
_EXPECTED_TAXONOMY = {
    "EMAIL",
    "PHONE",
    "SSN",
    "CREDIT_CARD",
    "IP_ADDRESS",
    "AWS_KEY",
    "API_KEY",
    "JWT",
    "IBAN",
    "ADDRESS",
    "PERSON_NAME",
    "DATE_OF_BIRTH",
}


def test_corpus_present_and_well_formed() -> None:
    docs = load_corpus(_CORPUS)
    assert len(docs) >= 1000
    for doc in docs:
        for start, end, _label in (*doc.gold, *doc.decoys):
            assert 0 <= start < end <= len(doc.text)


def test_corpus_taxonomy_is_exactly_the_intl_pack_types() -> None:
    docs = load_corpus(_CORPUS)
    assert set(canonical_labels(docs)) == _EXPECTED_TAXONOMY


def test_every_gold_type_has_a_gloss() -> None:
    docs = load_corpus(_CORPUS)
    for label in canonical_labels(docs):
        assert LABEL_DESCRIPTIONS.get(label), f"no LABEL_DESCRIPTIONS entry for {label}"


def test_competitor_maps_only_target_real_canonical_types() -> None:
    for mapping in (PRESIDIO_LABEL_MAP, MASK_PRIVACY_LABEL_MAP):
        assert set(mapping.values()) <= _EXPECTED_TAXONOMY


def test_naive_regex_adapter_runs_and_scores() -> None:
    docs = load_corpus(_CORPUS, limit=50)
    labels = canonical_labels(docs)
    naive = next(e for e in build_adapters(labels) if e[0].name == "naive_regex")
    preds = [naive[0].detect(doc.text) for doc in docs]
    partial = evaluate(docs, preds, naive[1], labels, MatchMode.PARTIAL)
    # A naive email/SSN regex must at least find *some* of each on 50 docs.
    assert partial["EMAIL"].tp > 0
    assert partial["SSN"].tp > 0


def test_hard_negatives_are_never_gold() -> None:
    docs = load_corpus(_CORPUS)
    gold_labels = {label for doc in docs for _s, _e, label in doc.gold}
    decoy_labels = {label for doc in docs for _s, _e, label in doc.decoys}
    assert decoy_labels.isdisjoint(gold_labels)
    assert decoy_labels  # the corpus does carry decoys
