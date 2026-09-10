"""ParityTally dict -> results.{json,md}."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .scoring import ParityTally


def to_json(doc_ids: list[str], tallies: dict[str, ParityTally], skipped: dict[str, str]) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "corpus": "indiapii-v1.0",
        "num_docs": len(doc_ids),
        "adapters": {
            name: {
                "docs": t.docs,
                "detection_parity": t.rate("detection_matches"),
                "roundtrip_exact": t.rate("roundtrip_exact"),
                "streaming_exact": t.rate("streaming_exact"),
                "extra_types": dict(t.extra_types),
                "missed_types": dict(t.missed_types),
                "roundtrip_fail_docs": t.roundtrip_fail_docs,
                "streaming_fail_docs": t.streaming_fail_docs,
            }
            for name, t in tallies.items()
        },
        "skipped": skipped,
    }


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.1%}"


def _divergence(t: ParityTally) -> str:
    bits = []
    if t.extra_types:
        got = ", ".join(f"{k}×{v}" for k, v in t.extra_types.most_common())
        bits.append(f"wrapper-only: {got}")
    if t.missed_types:
        missed = ", ".join(f"{k}×{v}" for k, v in t.missed_types.most_common())
        bits.append(f"wrapper-missed: {missed}")
    if t.roundtrip_fail_docs:
        bits.append(f"round-trip fail: {', '.join(t.roundtrip_fail_docs)}")
    if t.streaming_fail_docs:
        bits.append(f"streaming fail: {', '.join(t.streaming_fail_docs)}")
    return "; ".join(bits) if bits else "—"


def to_markdown(data: dict, tallies: dict[str, ParityTally]) -> str:
    lines = [
        "# integration-parity-v1 benchmark results",
        "",
        f"{data['num_docs']} documents from `indiapii-v1.0`, routed through each framework "
        "integration's masking layer and compared to `maskflow.mask()` / `maskflow.unmask()` "
        "(the `core` reference). Detection parity = the `(entity_type, value)` set the wrapper "
        "masks equals core's, per document. Round-trip = the wrapper's own unmask restores the "
        "document byte-exact. Streaming = the masked text fed back through the shared "
        "`StreamingUnmasker` at 1-byte and random chunk splits reassembles exactly. Every "
        "column should be 100% — a divergence is a wrapper bug.",
        "",
        "| integration | detection parity | round-trip | streaming | divergences |",
        "|---|---|---|---|---|",
    ]
    for name, t in tallies.items():
        lines.append(
            f"| {name} | {_pct(t.rate('detection_matches'))} | "
            f"{_pct(t.rate('roundtrip_exact'))} | {_pct(t.rate('streaming_exact'))} | "
            f"{_divergence(t)} |"
        )
    for name, reason in data["skipped"].items():
        lines.append(f"| {name} | skipped | skipped | skipped | {reason} |")
    lines.append("")
    return "\n".join(lines)


def write_report(
    out_dir: Path,
    doc_ids: list[str],
    tallies: dict[str, ParityTally],
    skipped: dict[str, str],
) -> None:
    data = to_json(doc_ids, tallies, skipped)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (out_dir / "results.md").write_text(to_markdown(data, tallies), encoding="utf-8")
