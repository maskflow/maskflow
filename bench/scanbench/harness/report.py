"""scan-log report = the shared harness report (strict/partial F1 +
latency) plus an "Audit cost" section: for a PII-exposure scan the metric
that matters is the false-positive rate -- how many log-noise tokens each
detector wrongly flags as PII per 1,000 records.
"""

from __future__ import annotations

from pathlib import Path

from bench.indiapii.harness.report import to_json_dict, write_json
from bench.indiapii.harness.report import to_markdown as _shared_markdown
from bench.indiapii.harness.runner import AdapterRunResult


def _fp_per_1000(r: AdapterRunResult, num_docs: int) -> tuple[float, int, float | None]:
    """(false positives / 1000 records, total FPs, overall precision) from
    the partial-overlap tally -- partial is the fair mode for 'did it flag
    noise', a strict boundary miss shouldn't count as a false alarm."""
    tp = sum(v.tp for v in r.partial.values())
    fp = sum(v.fp for v in r.partial.values())
    precision = tp / (tp + fp) if (tp + fp) else None
    return (fp / num_docs * 1000, fp, precision)


def _audit_cost_table(results: dict[str, AdapterRunResult], num_docs: int) -> str:
    lines = [
        "### Audit cost (false positives on log noise)",
        "",
        "| adapter | false positives / 1000 records | total FPs | overall precision |",
        "|---|---|---|---|",
    ]
    for name, r in results.items():
        if not r.available:
            lines.append(f"| {name} | skipped ({r.skipped_reason}) | | |")
            continue
        rate, fp, precision = _fp_per_1000(r, num_docs)
        p_str = f"{precision:.1%}" if precision is not None else "—"
        lines.append(f"| {name} | {rate:.1f} | {fp} | {p_str} |")
    return "\n".join(lines)


def write_report(
    out_dir: Path,
    corpus_name: str,
    num_docs: int,
    canonical_labels: tuple[str, ...],
    results: dict[str, AdapterRunResult],
    *,
    plumbing_note: str = "",
) -> None:
    data = to_json_dict(corpus_name, num_docs, canonical_labels, results)
    if plumbing_note:
        data["plumbing_check"] = plumbing_note
    write_json(out_dir / "results.json", data)

    md = _shared_markdown(corpus_name, num_docs, canonical_labels, results)
    parts = [md, _audit_cost_table(results, num_docs), ""]
    if plumbing_note:
        parts += [
            "### Scan-pipeline plumbing check",
            "",
            plumbing_note,
            "",
        ]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.md").write_text("\n".join(parts), encoding="utf-8")
