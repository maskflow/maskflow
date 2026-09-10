"""CI regression gate: `uv run pytest bench/scanbench/harness/tests -m benchmark`.

Only needs the maskflow_deep adapter -- no presidio, no API key. Scores a
deterministic first-400-record subset under partial-overlap matching and
fails if any entity's F1 drops more than 2.0 points below
bench/baselines-scan.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.indiapii.harness.corpus import load_corpus
from bench.indiapii.harness.matching import MatchMode, evaluate
from bench.scanbench.harness.adapters import build_adapters
from bench.scanbench.harness.labels import canonical_labels

_CORPUS = Path(__file__).resolve().parents[2] / "data" / "scan-log-v1.0.jsonl"
_BASELINES = Path(__file__).resolve().parents[3] / "baselines-scan.json"
_SUBSET = 400
_MAX_DROP = 2.0


@pytest.mark.benchmark
def test_maskflow_scan_f1_has_not_regressed_beyond_baseline() -> None:
    if not _BASELINES.exists():
        pytest.skip("no baseline -- run `make rebaseline-bench-scan` first")

    baseline = json.loads(_BASELINES.read_text(encoding="utf-8"))
    docs = load_corpus(_CORPUS, limit=_SUBSET)
    labels = canonical_labels(docs)
    entry = next(e for e in build_adapters(labels) if e[0].name == "maskflow_deep")
    preds = [entry[0].detect(doc.text) for doc in docs]
    partial = evaluate(docs, preds, entry[1], labels, MatchMode.PARTIAL)

    regressions = []
    for label, baseline_f1 in baseline.items():
        current = partial.get(label)
        current_f1 = current.f1 if current is not None else None
        if current_f1 is None:
            regressions.append(f"{label}: baseline {baseline_f1:.4f}, now no F1")
            continue
        drop = (baseline_f1 - current_f1) * 100
        if drop > _MAX_DROP:
            regressions.append(f"{label}: {baseline_f1:.4f} -> {current_f1:.4f} ({drop:.1f} pts)")
    assert not regressions, "F1 regression(s):\n" + "\n".join(regressions)
