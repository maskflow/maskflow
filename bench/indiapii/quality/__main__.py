"""CLI entry point: `uv run python -m bench.indiapii.quality <generate-tasks|run> ...`

The `run` subcommand needs an `ANTHROPIC_API_KEY` (the anthropic SDK's task
model + judge). Model ids default to `claude-sonnet-5` (task) and
`claude-opus-5` (judge); override with `--task-model` / `--judge-model` or
the `MASKFLOW_BENCH_QUALITY_TASK_MODEL` / `_JUDGE_MODEL` env vars. The run
is fully disk-cached (see cache.py), so a partial failure or an added task
only pays for what is new, and re-running to regenerate the report costs
nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from maskflow_bench.corpus import load_corpus

from .cache import DiskCache
from .judge import Judge
from .pipeline import TaskModel
from .report import write_report
from .runner import run_all
from .tasks import TASK_TYPES, Task, build_tasks, load_tasks, write_tasks

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


def _select_tasks(tasks: list[Task], limit: int | None, per_type: int | None) -> list[Task]:
    if per_type is not None:
        seen: dict[str, int] = {}
        picked: list[Task] = []
        for t in tasks:
            if seen.get(t.task_type, 0) < per_type:
                picked.append(t)
                seen[t.task_type] = seen.get(t.task_type, 0) + 1
        return picked
    if limit is not None:
        return tasks[:limit]
    return tasks


def _cmd_run(args: argparse.Namespace) -> int:
    docs = load_corpus(args.corpus)
    docs_by_id = {d.id: d for d in docs}
    tasks = _select_tasks(load_tasks(args.tasks), args.limit, args.sample_per_type)

    cache = DiskCache(args.cache_dir)
    model = TaskModel(cache, args.task_model)
    judge = Judge(cache, args.judge_model)

    for component in (model, judge):
        ok, reason = component.available()
        if not ok:
            print(f"{component.name} unavailable: {reason}", file=sys.stderr)
            return 1

    meta = {"task_model": model._model, "judge_model": judge._model}
    print(
        f"task_model={meta['task_model']} judge_model={meta['judge_model']} "
        f"tasks={len(tasks)} (x3 conditions x2 calls)",
        file=sys.stderr,
    )
    records = run_all(tasks, docs_by_id, model, judge)
    write_report(args.out, records, meta=meta)
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
    p_run.add_argument(
        "--sample-per-type",
        type=int,
        default=None,
        help=f"run the first N tasks of each type ({', '.join(TASK_TYPES)}) -- overrides --limit; "
        "handy for a cheap smoke run",
    )
    p_run.add_argument("--task-model", default=None, help="override the task model id")
    p_run.add_argument("--judge-model", default=None, help="override the judge model id")
    p_run.add_argument("--out", type=Path, default=Path("bench/reports") / "indiapii-quality-v1.0")
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
