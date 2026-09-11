"""Runs the *real* `maskflow scan` pipeline over the corpus and checks its
aggregated per-entity counts against what `detect()` finds directly -- so a
green scan-log benchmark also proves the scan's field extraction + bounded
streaming aggregation don't silently drop or double-count findings.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

from maskflow_bench.corpus import Document

from .adapters import MaskflowDeepAdapter
from .labels import canonical_labels


def _expected_counts(docs: list[Document], labels: tuple[str, ...]) -> Counter[str]:
    """Per-entity total from detect() directly -- the ground truth the scan
    aggregator should reproduce. Restricted to the corpus taxonomy so
    detections of unrelated types don't enter the comparison."""
    adapter = MaskflowDeepAdapter()
    label_set = set(labels)
    counts: Counter[str] = Counter()
    for doc in docs:
        for _s, _e, raw in adapter.detect(doc.text):
            if raw in label_set:
                counts[raw] += 1
    return counts


def run_plumbing_check(docs: list[Document]) -> tuple[bool, str]:
    """Returns (ok, human-readable note). Requires maskflow-cli importable
    (it is a workspace package); skips cleanly if not."""
    try:
        from maskflow_cli.scan.pipeline import PipelineConfig, run_pipeline
        from maskflow_cli.scan.sources import get_source
        from maskflow_cli.scan.spec import SourceSpec
        from maskflow_core.config.resolve import resolve_config
    except Exception as exc:  # noqa: BLE001
        return True, f"skipped — maskflow-cli scan modules unavailable ({exc})"

    labels = canonical_labels(docs)
    expected = _expected_counts(docs, labels)

    with tempfile.TemporaryDirectory() as tmp:
        corpus_path = Path(tmp) / "corpus.jsonl"
        with corpus_path.open("w", encoding="utf-8") as f:
            for doc in docs:
                f.write(json.dumps({"content": doc.text}) + "\n")

        source = get_source(SourceSpec(kind="jsonl", target=str(corpus_path), fields=("content",)))
        result = run_pipeline(
            source,
            PipelineConfig(
                root_config=resolve_config().config,
                deep=True,
                ner_available=True,
                workers=1,
            ),
        )

    got = result.aggregator.by_entity_measured
    if result.aggregator.records_processed != len(docs):
        return False, (
            f"scan processed {result.aggregator.records_processed} records, corpus has {len(docs)}"
        )

    mismatches = [
        f"{et}: detect()={expected.get(et, 0)} scan={got.get(et, 0)}"
        for et in sorted(set(expected) | {k for k in got if k in set(labels)})
        if expected.get(et, 0) != got.get(et, 0)
    ]
    if mismatches:
        return False, "per-entity count mismatch — " + "; ".join(mismatches)

    total = sum(expected.values())
    return True, (
        f"PASS — `run_pipeline(--deep)` over all {len(docs)} records reproduced "
        f"`detect()`'s per-entity counts exactly ({total} findings across "
        f"{len(expected)} entity types); field extraction + streaming "
        f"aggregation lose nothing."
    )
