"""indiapii-tabular-v1.0: the committed corpus must be exactly what the
generator produces from its seed (cheap, unmarked), and MaskFlow's partial
F1 on a 60-doc subset must not drop more than 2 points below
bench/baselines-tabular.json (`-m benchmark`, maskflow adapter only --
same gate shape as bench/indiapii/harness/tests/test_ci_regression.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from maskflow_bench.labels import canonical_labels
from maskflow_bench.loader import load_my_data
from maskflow_bench.matching import MatchMode, evaluate

from bench.indiapii.harness.adapters import build_adapters
from bench.tabular.generate import OUT, _serialise, generate

_BASELINES = Path(__file__).resolve().parents[2] / "baselines-tabular.json"
_SUBSET = 60
_MAX_DROP = 2.0  # percentage points


def test_committed_corpus_is_reproducible_from_seed() -> None:
    assert OUT.read_text(encoding="utf-8") == _serialise(generate()), (
        "committed corpus drifted from the generator -- run `python -m bench.tabular.generate`"
    )


def test_every_gold_span_is_inside_a_single_table_cell() -> None:
    for line in OUT.read_text(encoding="utf-8").splitlines():
        doc = json.loads(line)
        for entity in doc["entities"]:
            value = doc["text"][entity["start"] : entity["end"]]
            assert value and value == value.strip()
            assert not any(sep in value for sep in ("\n", "\t", "|", ","))


@pytest.mark.benchmark
def test_maskflow_f1_has_not_regressed_beyond_baseline() -> None:
    baseline = json.loads(_BASELINES.read_text(encoding="utf-8"))
    docs = load_my_data(OUT, limit=_SUBSET)
    labels = canonical_labels(docs)
    adapter, label_map = next(e for e in build_adapters(labels) if e[0].name == "maskflow")
    predictions = [adapter.detect(doc.text) for doc in docs]
    partial = evaluate(docs, predictions, label_map, labels, MatchMode.PARTIAL)

    regressions = []
    for label, baseline_f1 in baseline.items():
        current = partial.get(label)
        current_f1 = current.f1 if current is not None else None
        if current_f1 is None:
            regressions.append(f"{label}: baseline {baseline_f1:.4f}, now has no F1")
            continue
        drop_points = (baseline_f1 - current_f1) * 100
        if drop_points > _MAX_DROP:
            regressions.append(
                f"{label}: baseline {baseline_f1:.4f} -> {current_f1:.4f} "
                f"({drop_points:.1f} points, max allowed {_MAX_DROP})"
            )

    assert not regressions, "F1 regression(s) beyond baseline:\n" + "\n".join(regressions)
