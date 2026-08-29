"""Writes results.json (full structured data) and results.md (generated
tables) from a run_all() result. Module path is
`bench.indiapii.harness.report`, distinct from the unrelated, pre-existing
`bench.indiapii.report` (the pack-india L1-L3 dev accuracy report) -- see
harness/__init__.py's docstring.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .matching import PRFResult
from .runner import AdapterRunResult


def _prf_to_dict(r: PRFResult) -> dict[str, float | int | None]:
    return {
        "precision": r.precision,
        "recall": r.recall,
        "f1": r.f1,
        "tp": r.tp,
        "fp": r.fp,
        "fn": r.fn,
    }


def to_json_dict(
    corpus_name: str,
    num_docs: int,
    canonical_labels: tuple[str, ...],
    results: dict[str, AdapterRunResult],
) -> dict:
    adapters: dict[str, dict] = {}
    for name, r in results.items():
        entry: dict = {"available": r.available, "skipped_reason": r.skipped_reason}
        if r.available:
            entry["strict"] = {label: _prf_to_dict(v) for label, v in r.strict.items()}
            entry["partial"] = {label: _prf_to_dict(v) for label, v in r.partial.items()}
            if r.profile is not None:
                entry["latency_ms_per_kb"] = r.profile.latency_ms_per_kb
                entry["median_doc_ms"] = r.profile.median_doc_ms
                entry["p95_doc_ms"] = r.profile.p95_doc_ms
                entry["peak_memory_mb"] = r.profile.peak_memory_mb
                entry["doc_errors"] = r.profile.errors
        adapters[name] = entry
    return {
        "corpus": corpus_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "num_docs": num_docs,
        "canonical_labels": list(canonical_labels),
        "adapters": adapters,
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _f1_cell(results: dict[str, AdapterRunResult], adapter_name: str, mode: str, label: str) -> str:
    r = results[adapter_name]
    if not r.available:
        return "skipped"
    prf = getattr(r, mode).get(label)
    if prf is None or prf.f1 is None:
        return "—"
    return f"{prf.f1:.1%}"


def _pivot_table(
    results: dict[str, AdapterRunResult],
    adapter_names: list[str],
    canonical_labels: tuple[str, ...],
    mode: str,
    title: str,
) -> str:
    header = "| entity_type | " + " | ".join(adapter_names) + " |"
    sep = "|---" * (len(adapter_names) + 1) + "|"
    lines = [f"### {title}", "", header, sep]
    for label in canonical_labels:
        row = [_f1_cell(results, name, mode, label) for name in adapter_names]
        lines.append(f"| {label} | " + " | ".join(row) + " |")
    return "\n".join(lines)


def _latency_table(results: dict[str, AdapterRunResult], adapter_names: list[str]) -> str:
    header = "| adapter | ms/KB | median ms/doc | p95 ms/doc | peak memory (MB) | doc errors |"
    sep = "|---|---|---|---|---|---|"
    lines = ["### Latency & memory", "", header, sep]
    for name in adapter_names:
        r = results[name]
        if not r.available:
            lines.append(f"| {name} | skipped ({r.skipped_reason}) | | | | |")
            continue
        p = r.profile
        assert p is not None
        lines.append(
            f"| {name} | {p.latency_ms_per_kb:.3f} | {p.median_doc_ms:.3f} | "
            f"{p.p95_doc_ms:.3f} | {p.peak_memory_mb:.1f} | {p.errors} |"
        )
    return "\n".join(lines)


def to_markdown(
    corpus_name: str,
    num_docs: int,
    canonical_labels: tuple[str, ...],
    results: dict[str, AdapterRunResult],
) -> str:
    adapter_names = list(results.keys())
    parts = [
        f"# {corpus_name} benchmark results",
        "",
        f"{num_docs} documents, {len(canonical_labels)} canonical entity types. "
        'F1 shown per entity per adapter; "—" means the adapter produced no '
        'matching predictions or the entity has no gold spans in this run; "skipped" '
        "means the adapter's dependency/API key wasn't available in this environment.",
        "",
        _pivot_table(results, adapter_names, canonical_labels, "strict", "Strict-span F1"),
        "",
        _pivot_table(results, adapter_names, canonical_labels, "partial", "Partial-overlap F1"),
        "",
        _latency_table(results, adapter_names),
        "",
    ]
    return "\n".join(parts)


def write_report(
    out_dir: Path,
    corpus_name: str,
    num_docs: int,
    canonical_labels: tuple[str, ...],
    results: dict[str, AdapterRunResult],
) -> None:
    data = to_json_dict(corpus_name, num_docs, canonical_labels, results)
    write_json(out_dir / "results.json", data)
    md = to_markdown(corpus_name, num_docs, canonical_labels, results)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.md").write_text(md, encoding="utf-8")
