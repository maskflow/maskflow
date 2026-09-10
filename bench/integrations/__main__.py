"""CLI: `uv run python -m bench.integrations run [--limit N] [--out DIR]`

Needs the integration packages:
    uv sync --all-extras --group litellm --group llama-index --group mcp
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .harness import run_parity
from .report import write_report

_DEFAULT_OUT = Path("bench/reports/integration-parity-v1")


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m bench.integrations")
    sub = ap.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="run the parity harness and write a report")
    p_run.add_argument("--limit", type=int, default=300, help="corpus docs (first N); 0 = all")
    p_run.add_argument("--corpus", type=Path, default=None)
    p_run.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = ap.parse_args()

    limit = None if args.limit == 0 else args.limit
    doc_ids, tallies, skipped = run_parity(corpus=args.corpus, limit=limit)
    write_report(args.out, doc_ids, tallies, skipped)

    for name, t in tallies.items():
        print(
            f"{name}: detection {t.rate('detection_matches'):.1%} "
            f"round-trip {t.rate('roundtrip_exact'):.1%} "
            f"streaming {t.rate('streaming_exact'):.1%}",
            file=sys.stderr,
        )
    for name, reason in skipped.items():
        print(f"{name}: skipped — {reason}", file=sys.stderr)
    print(f"wrote {args.out / 'results.json'} and {args.out / 'results.md'}", file=sys.stderr)

    perfect = all(
        t.detection_matches == t.docs == t.roundtrip_exact == t.streaming_exact
        for t in tallies.values()
    )
    return 0 if perfect else 1


if __name__ == "__main__":
    raise SystemExit(main())
