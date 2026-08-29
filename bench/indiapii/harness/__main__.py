"""CLI entry point: `uv run python -m bench.indiapii.harness <run|rebaseline> ...`"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import build_adapters
from .corpus import load_corpus
from .labels import canonical_labels as compute_canonical_labels
from .matching import MatchMode, evaluate
from .report import write_report
from .runner import run_all

_DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "data" / "indiapii-v1.0.jsonl"


def _cmd_run(args: argparse.Namespace) -> int:
    docs = load_corpus(args.corpus, limit=args.limit)
    labels = compute_canonical_labels(docs)
    entries = build_adapters(labels)
    if args.adapters != "all":
        wanted = set(args.adapters.split(","))
        entries = [e for e in entries if e[0].name in wanted]
        missing = wanted - {e[0].name for e in entries}
        if missing:
            print(f"unknown adapter(s): {sorted(missing)}", file=sys.stderr)
            return 1

    results = run_all(entries, docs, labels)
    write_report(args.out, args.corpus.stem, len(docs), labels, results)

    for name, r in results.items():
        status = "ok" if r.available else f"skipped ({r.skipped_reason})"
        print(f"{name}: {status}", file=sys.stderr)
    print(f"wrote {args.out / 'results.json'} and {args.out / 'results.md'}", file=sys.stderr)
    return 0


def _cmd_rebaseline(args: argparse.Namespace) -> int:
    """Re-runs only the maskflow adapter over the deterministic first-N-doc
    subset and overwrites bench/baselines.json with its partial-overlap F1
    per entity, printing a diff of what moved (see test_ci_regression.py
    for how this file is consumed)."""
    docs = load_corpus(args.corpus, limit=args.subset)
    labels = compute_canonical_labels(docs)
    maskflow_entry = next(e for e in build_adapters(labels) if e[0].name == "maskflow")

    predictions_by_doc = [maskflow_entry[0].detect(doc.text) for doc in docs]
    partial = evaluate(docs, predictions_by_doc, maskflow_entry[1], labels, MatchMode.PARTIAL)
    new_baseline = {label: r.f1 for label, r in partial.items() if r.f1 is not None}

    old_baseline: dict[str, float] = {}
    if args.out.exists():
        old_baseline = json.loads(args.out.read_text(encoding="utf-8"))

    for label in sorted(set(old_baseline) | set(new_baseline)):
        old_v = old_baseline.get(label)
        new_v = new_baseline.get(label)
        if old_v == new_v:
            continue
        old_s = f"{old_v:.4f}" if old_v is not None else "—"
        new_s = f"{new_v:.4f}" if new_v is not None else "—"
        print(f"{label}: {old_s} -> {new_s}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(new_baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.indiapii.harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run all (or selected) adapters and write a report")
    p_run.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    p_run.add_argument("--adapters", default="all", help="comma-separated adapter names, or 'all'")
    p_run.add_argument("--limit", type=int, default=None, help="only score the first N docs")
    p_run.add_argument("--out", type=Path, default=Path("bench/reports") / _DEFAULT_CORPUS.stem)
    p_run.set_defaults(func=_cmd_run)

    p_rebaseline = sub.add_parser(
        "rebaseline", help="re-run the maskflow adapter on a fixed subset, overwrite baselines.json"
    )
    p_rebaseline.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    p_rebaseline.add_argument("--subset", type=int, default=200)
    p_rebaseline.add_argument("--out", type=Path, default=Path("bench/baselines.json"))
    p_rebaseline.set_defaults(func=_cmd_rebaseline)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
