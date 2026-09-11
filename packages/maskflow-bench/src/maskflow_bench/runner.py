"""Orchestrates: for each adapter, check availability, run detect() once
per document (timed, error-guarded), then score the same cached
predictions under both matching modes -- no adapter's detect() is ever
called twice for the same document.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .adapters import AdapterEntry
from .corpus import Document
from .matching import MatchMode, PRFResult, evaluate
from .profiling import Profiler, ProfileResult


@dataclass
class AdapterRunResult:
    name: str
    available: bool
    skipped_reason: str = ""
    strict: dict[str, PRFResult] = field(default_factory=dict)
    partial: dict[str, PRFResult] = field(default_factory=dict)
    profile: ProfileResult | None = None


def run_adapter(
    entry: AdapterEntry, docs: list[Document], canonical_labels: tuple[str, ...]
) -> AdapterRunResult:
    adapter, label_map = entry
    ok, reason = adapter.available()
    if not ok:
        return AdapterRunResult(name=adapter.name, available=False, skipped_reason=reason)

    # One untimed warm-up call so a one-time cost every adapter pays somewhere
    # (spaCy model load, first-call JIT/regex compilation, ...) lands the same
    # way for all of them -- some adapters already pay it inside available()
    # (e.g. presidio's engine construction), others pay it lazily on their
    # first detect() call (maskflow's NER pass) -- without this, whichever
    # adapter happens to defer its warm-up into the timed loop looks
    # artificially slower for reasons that have nothing to do with steady-
    # state per-document latency, which is what ms/KB is meant to measure.
    try:
        adapter.detect("warm-up, no PII here.")
    except Exception:  # noqa: BLE001 -- warm-up failures don't affect timing/scoring
        pass

    profiler = Profiler()
    profiler.start()
    predictions_by_doc: list[list[tuple[int, int, str]]] = []
    for doc in docs:
        t0 = time.perf_counter()
        try:
            preds = adapter.detect(doc.text)
        except Exception:  # noqa: BLE001 -- one bad doc must not sink the whole adapter run
            preds = []
            profiler.errors += 1
        profiler.record(time.perf_counter() - t0, doc.size_bytes)
        predictions_by_doc.append(preds)

    strict = evaluate(docs, predictions_by_doc, label_map, canonical_labels, MatchMode.STRICT)
    partial = evaluate(docs, predictions_by_doc, label_map, canonical_labels, MatchMode.PARTIAL)

    return AdapterRunResult(
        name=adapter.name,
        available=True,
        strict=strict,
        partial=partial,
        profile=profiler.finish(),
    )


def run_all(
    entries: list[AdapterEntry], docs: list[Document], canonical_labels: tuple[str, ...]
) -> dict[str, AdapterRunResult]:
    return {entry[0].name: run_adapter(entry, docs, canonical_labels) for entry in entries}
