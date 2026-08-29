"""CLI entry point: `uv run python -m bench.indiapii.quality <generate-tasks|run> ...`"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bench.indiapii.harness.corpus import load_corpus

from .cache import DiskCache
from .judge import Judge
from .pipeline import TaskModel
from .report import write_report
from .runner import run_all
from .tasks import build_tasks, load_tasks, write_tasks

_DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "data" / "indiapii-v1.0.jsonl"
_DEFAULT_TASKS = Path(__file__).resolve().parent / "data" / "quality-v1.0.jsonl"
_DEFAULT_CACHE = Path(__file__).resolve().parent / ".cache"
_DEFAULT_SEED = 20260830


def _cmd_generate_tasks(args: argparse.Namespace) -> int:
    docs = load_corpus(args.corpus)
    tasks = build_tasks(docs, seed=args.seed)
    write_tasks(tasks, args.out)
    print(f"wrote {len(tasks)} tasks to {args.out}", file=sys.stderr)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    docs = load_corpus(args.corpus)
    docs_by_id = {d.id: d for d in docs}
    tasks = load_tasks(args.tasks)
    if args.limit is not None:
        tasks = tasks[: args.limit]

    cache = DiskCache(args.cache_dir)
    model = TaskModel(cache)
    judge = Judge(cache)

    ok, reason = model.available()
    if not ok:
        print(f"task model unavailable: {reason}", file=sys.stderr)
        return 1
    ok, reason = judge.available()
    if not ok:
        print(f"judge unavailable: {reason}", file=sys.stderr)
        return 1

    records = run_all(tasks, docs_by_id, model, judge)
    write_report(args.out, records)
    print(f"wrote {args.out / 'results.json'} and {args.out / 'results.md'}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.indiapii.quality")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser(
        "generate-tasks", help="build quality-v1.0.jsonl from the indiapii-v1.0 corpus"
    )
    p_gen.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    p_gen.add_argument("--seed", type=int, default=_DEFAULT_SEED)
    p_gen.add_argument("--out", type=Path, default=_DEFAULT_TASKS)
    p_gen.set_defaults(func=_cmd_generate_tasks)

    p_run = sub.add_parser("run", help="run all tasks x conditions and write a report")
    p_run.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    p_run.add_argument("--tasks", type=Path, default=_DEFAULT_TASKS)
    p_run.add_argument("--cache-dir", type=Path, default=_DEFAULT_CACHE)
    p_run.add_argument("--limit", type=int, default=None, help="only run the first N tasks")
    p_run.add_argument("--out", type=Path, default=Path("bench/reports") / "indiapii-quality-v1.0")
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
