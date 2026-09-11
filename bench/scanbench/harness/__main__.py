"""CLI: `uv run python -m bench.scanbench.harness <run|rebaseline> ...`

Scoring internals are bench.indiapii.harness's; only the adapters, label
maps, the audit-cost section, and the scan-pipeline plumbing check are
scan-specific.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from maskflow_bench.corpus import load_corpus
from maskflow_bench.matching import MatchMode, evaluate
from maskflow_bench.runner import run_all

from .adapters import build_adapters
from .labels import canonical_labels as compute_canonical_labels
from .plumbing import run_plumbing_check
from .report import write_report

_HERE = Path(__file__).resolve().parents[1]
_DEFAULT_CORPUS = _HERE / "data" / "scan-log-v1.0.jsonl"
_REPO_ROOT = _HERE.parents[1]


def _cmd_run(args: argparse.Namespace) -> int:
    docs = load_corpus(args.corpus, limit=args.limit)
    labels = compute_canonical_labels(docs)
    entries = build_adapters(labels)
    if args.adapters != "all":
        wanted = set(args.adapters.split(","))
        entries = [e for e in entries if e[0].name in wanted]

    results = run_all(entries, docs, labels)

    plumbing_note = ""
    if not args.no_plumbing:
        ok, plumbing_note = run_plumbing_check(docs)
        print(f"plumbing check: {'ok' if ok else 'FAIL'} — {plumbing_note}", file=sys.stderr)
        if not ok:
            return 1

    write_report(
        args.out, args.corpus.stem, len(docs), labels, results, plumbing_note=plumbing_note
    )
    for name, r in results.items():
        print(
            f"{name}: {'ok' if r.available else f'skipped ({r.skipped_reason})'}", file=sys.stderr
        )
    print(f"wrote {args.out / 'results.json'} and {args.out / 'results.md'}", file=sys.stderr)
    return 0


def _cmd_rebaseline(args: argparse.Namespace) -> int:
    docs = load_corpus(args.corpus, limit=args.subset)
    labels = compute_canonical_labels(docs)
    entry = next(e for e in build_adapters(labels) if e[0].name == "maskflow_deep")
    preds = [entry[0].detect(doc.text) for doc in docs]
    partial = evaluate(docs, preds, entry[1], labels, MatchMode.PARTIAL)
    new_baseline = {label: r.f1 for label, r in partial.items() if r.f1 is not None}

    old = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    for label in sorted(set(old) | set(new_baseline)):
        o, n = old.get(label), new_baseline.get(label)
        if o != n:
            print(
                f"{label}: {o if o is None else f'{o:.4f}'} -> {n if n is None else f'{n:.4f}'}",
                file=sys.stderr,
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(new_baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.scanbench.harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run all (or selected) adapters and write a report")
    p_run.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    p_run.add_argument("--adapters", default="all", help="comma-separated adapter names, or 'all'")
    p_run.add_argument("--limit", type=int, default=None)
    p_run.add_argument("--no-plumbing", action="store_true", help="skip the run_pipeline check")
    p_run.add_argument(
        "--out", type=Path, default=_REPO_ROOT / "bench" / "reports" / _DEFAULT_CORPUS.stem
    )
    p_run.set_defaults(func=_cmd_run)

    p_rb = sub.add_parser("rebaseline", help="overwrite baselines-scan.json from maskflow_deep")
    p_rb.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    p_rb.add_argument("--subset", type=int, default=400)
    p_rb.add_argument("--out", type=Path, default=_REPO_ROOT / "bench" / "baselines-scan.json")
    p_rb.set_defaults(func=_cmd_rebaseline)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
