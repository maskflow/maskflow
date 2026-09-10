"""Run every available integration adapter over a corpus subset and tally
its parity against the `core` reference."""

from __future__ import annotations

from pathlib import Path

from bench.indiapii.harness.corpus import load_corpus

from .adapters import ALL_ADAPTERS, CoreAdapter
from .scoring import ParityTally, compare

_DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "indiapii" / "data" / "indiapii-v1.0.jsonl"


def run_parity(
    *, corpus: Path | None = None, limit: int | None = 300
) -> tuple[list[str], dict[str, ParityTally], dict[str, str]]:
    """Returns (doc_ids, {adapter_name: ParityTally}, {skipped_name: reason})."""
    docs = load_corpus(corpus or _DEFAULT_CORPUS, limit=limit)
    doc_ids = [d.id for d in docs]

    core = CoreAdapter()
    core_runs = {d.id: core.run(d.text) for d in docs}

    tallies: dict[str, ParityTally] = {}
    skipped: dict[str, str] = {}
    for adapter in ALL_ADAPTERS:
        if adapter.name == "core":
            continue
        ok, reason = adapter.available()
        if not ok:
            skipped[adapter.name] = reason
            continue
        tally = ParityTally(name=adapter.name)
        for doc in docs:
            compare(tally, doc.id, doc.text, adapter.run(doc.text), core_runs[doc.id])
        tallies[adapter.name] = tally

    return doc_ids, tallies, skipped
