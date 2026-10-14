"""Score MaskFlow on indiapii-tabular-v1.0 and write results.json/results.md.

    uv run python -m bench.tabular.score [--limit N] [--out DIR]

Decoy columns (order IDs, internal account IDs, ...) are unlabelled, so any
span MaskFlow predicts inside one is counted as a false positive for the
entity type it predicted -- precision here is the "doesn't over-mask
lookalike columns" number.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from maskflow_bench.labels import canonical_labels
from maskflow_bench.loader import load_my_data
from maskflow_bench.report import write_report
from maskflow_bench.runner import run_adapter

from bench.indiapii.harness.adapters import build_adapters
from bench.tabular.generate import OUT as CORPUS
from bench.tabular.generate import VERSION


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.tabular.score")
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("bench/reports") / VERSION)
    args = parser.parse_args()

    docs = load_my_data(args.corpus, limit=args.limit)
    labels = canonical_labels(docs)
    entry = next(e for e in build_adapters(labels) if e[0].name == "maskflow")
    result = run_adapter(entry, docs, labels)
    write_report(args.out, VERSION, len(docs), labels, {result.name: result})

    print(f"{VERSION}: {len(docs)} docs -> {args.out}")

    def pct(value: float | None) -> str:
        return "  n/a" if value is None else f"{value:.3f}"

    for label in labels:
        r = result.strict.get(label)
        if r is not None:
            print(
                f"  {label:16} P {pct(r.precision)}  R {pct(r.recall)}  F1 {pct(r.f1)}  FP {r.fp}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
