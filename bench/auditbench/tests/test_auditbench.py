"""The CI gate: discovery and classification must not regress."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.auditbench.score import MAX_DROP, score_all

_BASELINE = Path(__file__).resolve().parents[3] / "bench" / "baselines-audit.json"


def test_every_fixture_is_scored() -> None:
    scores = score_all()
    assert scores["discovery_recall"].total == 8, (
        "the six fixture apps contain eight expected flows; a change in that "
        "count means a fixture or its expected.json moved"
    )


def test_discovery_finds_every_expected_flow() -> None:
    """Recall is the metric that matters most.

    A missed sink produces a clean report for a leaking application, which
    is strictly worse than a false positive.
    """
    assert score_all()["discovery_recall"].value == 1.0


def test_classification_is_exact_on_the_fixtures() -> None:
    assert score_all()["classification_accuracy"].value == 1.0


@pytest.mark.benchmark
def test_no_metric_has_regressed_beyond_baseline() -> None:
    if not _BASELINE.exists():
        pytest.skip(f"no baseline at {_BASELINE} -- run `make rebaseline-audit` first")

    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    scores = score_all()

    regressions = []
    for name, was in baseline.items():
        if was is None:
            continue
        current = scores[name].value if name in scores else None
        if current is None:
            regressions.append(f"{name}: baseline {was:.4f}, now undefined")
            continue
        drop = (was - current) * 100
        if drop > MAX_DROP:
            regressions.append(
                f"{name}: baseline {was:.4f} -> {current:.4f} "
                f"({drop:.1f} points, max allowed {MAX_DROP})"
            )

    assert not regressions, "regression(s) beyond baseline:\n" + "\n".join(regressions)
