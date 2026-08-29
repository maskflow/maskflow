"""Aggregates TaskConditionRecords into per-task_type x condition summary
statistics (mean judge dimensions, mean field-accuracy F1, leak rate) plus
paired bootstrap-CI deltas of each masked condition against unmasked --
writes results.json (every record + aggregates) and results.md (a summary
table), the same JSON+Markdown convention as harness/report.py.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .pipeline import CONDITIONS
from .runner import TaskConditionRecord
from .scoring import bootstrap_ci
from .tasks import TASK_TYPES

_JUDGE_DIMS = ("task_completion", "fluency", "factual_consistency")
_MASKED_CONDITIONS = ("placeholder", "surrogate")


def _mean_ci(values: list[float]) -> dict[str, float | int]:
    mean, lo, hi = bootstrap_ci(values)
    return {"mean": mean, "ci_low": lo, "ci_high": hi, "n": len(values)}


def _field_f1s(records: list[TaskConditionRecord]) -> list[float]:
    return [
        r.field_accuracy.f1
        for r in records
        if r.field_accuracy is not None and r.field_accuracy.f1 is not None
    ]


def aggregate(records: list[TaskConditionRecord]) -> dict:
    by_type_condition: dict[tuple[str, str], list[TaskConditionRecord]] = defaultdict(list)
    by_task_condition: dict[tuple[str, str], TaskConditionRecord] = {}
    task_ids_by_type: dict[str, list[str]] = defaultdict(list)
    seen_task_ids: set[str] = set()

    for r in records:
        by_type_condition[(r.task_type, r.condition)].append(r)
        by_task_condition[(r.task_id, r.condition)] = r
        if r.task_id not in seen_task_ids:
            seen_task_ids.add(r.task_id)
            task_ids_by_type[r.task_type].append(r.task_id)

    result: dict = {"task_types": {}}
    for task_type in TASK_TYPES:
        entry: dict = {"conditions": {}}
        for condition in CONDITIONS:
            group = by_type_condition.get((task_type, condition), [])
            cond_entry: dict = {
                dim: _mean_ci([getattr(r, dim) for r in group if getattr(r, dim) is not None])
                for dim in _JUDGE_DIMS
            }
            cond_entry["leak_rate"] = (
                sum(r.leaked_placeholder for r in group) / len(group) if group else None
            )
            if task_type == "extract_fields":
                cond_entry["field_f1"] = _mean_ci(_field_f1s(group))
            cond_entry["n"] = len(group)
            entry["conditions"][condition] = cond_entry

        deltas: dict[str, dict] = {}
        for condition in _MASKED_CONDITIONS:
            per_dim_deltas: dict[str, list[float]] = {dim: [] for dim in _JUDGE_DIMS}
            field_f1_deltas: list[float] = []
            for task_id in task_ids_by_type[task_type]:
                base = by_task_condition.get((task_id, "unmasked"))
                other = by_task_condition.get((task_id, condition))
                if base is None or other is None:
                    continue
                for dim in _JUDGE_DIMS:
                    b, o = getattr(base, dim), getattr(other, dim)
                    if b is not None and o is not None:
                        per_dim_deltas[dim].append(o - b)
                if (
                    task_type == "extract_fields"
                    and base.field_accuracy
                    and other.field_accuracy
                    and base.field_accuracy.f1 is not None
                    and other.field_accuracy.f1 is not None
                ):
                    field_f1_deltas.append(other.field_accuracy.f1 - base.field_accuracy.f1)
            delta_entry = {dim: _mean_ci(vals) for dim, vals in per_dim_deltas.items()}
            if task_type == "extract_fields":
                delta_entry["field_f1"] = _mean_ci(field_f1_deltas)
            deltas[condition] = delta_entry
        entry["deltas_vs_unmasked"] = deltas
        result["task_types"][task_type] = entry
    return result


def to_json_dict(records: list[TaskConditionRecord]) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "num_records": len(records),
        "records": [asdict(r) for r in records],
        "aggregate": aggregate(records),
    }


def _fmt_delta(cell: dict | None) -> str:
    if not cell or not cell.get("n"):
        return "—"
    return f"{cell['mean']:+.2f} [{cell['ci_low']:+.2f}, {cell['ci_high']:+.2f}]"


def _fmt_mean(cell: dict | None) -> str:
    if not cell or not cell.get("n"):
        return "—"
    return f"{cell['mean']:.2f}"


def to_markdown(data: dict) -> str:
    lines = [
        "# indiapii-quality-v1.0 benchmark results",
        "",
        f"{data['num_records']} (task, condition) records. Judge dimensions are "
        "1-5. Deltas are masked-minus-unmasked, paired per task instance, with a "
        "95% CI from a 2000-resample nonparametric bootstrap.",
        "",
    ]
    for task_type, entry in data["aggregate"]["task_types"].items():
        lines.append(f"## {task_type}")
        lines.append("")
        lines.append(
            "| condition | task_completion | fluency | factual_consistency "
            "| leak_rate | field_f1 | n |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for condition in CONDITIONS:
            c = entry["conditions"].get(condition, {})
            leak = c.get("leak_rate")
            leak_s = f"{leak:.1%}" if leak is not None else "—"
            lines.append(
                f"| {condition} | {_fmt_mean(c.get('task_completion'))} | "
                f"{_fmt_mean(c.get('fluency'))} | {_fmt_mean(c.get('factual_consistency'))} | "
                f"{leak_s} | {_fmt_mean(c.get('field_f1'))} | {c.get('n', 0)} |"
            )
        lines.append("")
        lines.append("Delta vs. unmasked (95% CI):")
        lines.append("")
        lines.append("| condition | task_completion | fluency | factual_consistency | field_f1 |")
        lines.append("|---|---|---|---|---|")
        for condition in _MASKED_CONDITIONS:
            d = entry["deltas_vs_unmasked"].get(condition, {})
            lines.append(
                f"| {condition} | {_fmt_delta(d.get('task_completion'))} | "
                f"{_fmt_delta(d.get('fluency'))} | {_fmt_delta(d.get('factual_consistency'))} | "
                f"{_fmt_delta(d.get('field_f1'))} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_report(out_dir: Path, records: list[TaskConditionRecord]) -> None:
    data = to_json_dict(records)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (out_dir / "results.md").write_text(to_markdown(data), encoding="utf-8")
