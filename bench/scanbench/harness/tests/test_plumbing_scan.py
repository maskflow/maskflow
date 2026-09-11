"""The scan-pipeline plumbing check on a small corpus slice: the real
`maskflow scan` pipeline must reproduce `detect()`'s per-entity counts.
Marked `benchmark` -- it runs the full deep pipeline (spaCy).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from maskflow_bench.corpus import load_corpus

from bench.scanbench.harness.plumbing import run_plumbing_check

_CORPUS = Path(__file__).resolve().parents[2] / "data" / "scan-log-v1.0.jsonl"


@pytest.mark.benchmark
def test_scan_pipeline_reproduces_detect_counts_on_a_slice() -> None:
    ok, note = run_plumbing_check(load_corpus(_CORPUS, limit=150))
    assert ok, note
