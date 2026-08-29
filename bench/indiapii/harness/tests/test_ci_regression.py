"""The CI regression gate: `uv run pytest bench/indiapii/harness/tests -m benchmark`.

Only ever needs the maskflow adapter -- zero extra dependencies, safe on
every existing CI matrix leg (no presidio/mask-privacy install, no
Anthropic key). Scores a deterministic first-200-doc subset of the corpus
under partial-overlap matching (more stable doc-to-doc than exact-offset
strict matching -- see bench/indiapii/harness's plan) and fails if any
entity's F1 drops more than 2.0 points below bench/baselines.json.

An entity with no baseline entry yet is skipped, not failed, so adding a
new entity type to the corpus/pack doesn't retroactively break CI before
`make rebaseline-bench` has ever recorded a number for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.indiapii.harness.adapters import build_adapters
from bench.indiapii.harness.corpus import load_corpus
from bench.indiapii.harness.labels import canonical_labels
from bench.indiapii.harness.matching import MatchMode, evaluate

_CORPUS = Path(__file__).resolve().parents[2] / "data" / "indiapii-v1.0.jsonl"
_BASELINES = Path(__file__).resolve().parents[3] / "baselines.json"
_SUBSET = 200
_MAX_DROP = 2.0  # percentage points


@pytest.mark.benchmark
def test_maskflow_f1_has_not_regressed_beyond_baseline() -> None:
    if not _BASELINES.exists():
        pytest.skip(f"no baseline file at {_BASELINES} -- run `make rebaseline-bench` first")

    baseline = json.loads(_BASELINES.read_text(encoding="utf-8"))
    docs = load_corpus(_CORPUS, limit=_SUBSET)
    labels = canonical_labels(docs)
    maskflow_entry = next(e for e in build_adapters(labels) if e[0].name == "maskflow")

    predictions_by_doc = [maskflow_entry[0].detect(doc.text) for doc in docs]
    partial = evaluate(docs, predictions_by_doc, maskflow_entry[1], labels, MatchMode.PARTIAL)

    regressions = []
    for label, baseline_f1 in baseline.items():
        current = partial.get(label)
        current_f1 = current.f1 if current is not None else None
        if current_f1 is None:
            regressions.append(f"{label}: baseline {baseline_f1:.4f}, now has no F1 (0 tp/fp/fn)")
            continue
        drop_points = (baseline_f1 - current_f1) * 100
        if drop_points > _MAX_DROP:
            regressions.append(
                f"{label}: baseline {baseline_f1:.4f} -> {current_f1:.4f} "
                f"({drop_points:.1f} points, max allowed {_MAX_DROP})"
            )

    assert not regressions, "F1 regression(s) beyond baseline:\n" + "\n".join(regressions)
