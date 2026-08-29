"""Orchestrates: for each task, for each of the three masking conditions,
run the pipeline, judge the final response, and score fields where the
task type allows. Every step goes through DiskCache (see cache.py / judge.py
/ pipeline.py), so a rerun after a partial failure or an added task only
pays for what's new.
"""

from __future__ import annotations

from dataclasses import dataclass

from bench.indiapii.harness.corpus import Document

from . import prompts
from .judge import Judge
from .pipeline import CONDITIONS, TaskModel, run_condition
from .scoring import FieldAccuracy, has_leak, score_fields
from .tasks import Task


@dataclass(frozen=True)
class TaskConditionRecord:
    task_id: str
    domain: str
    task_type: str
    condition: str
    task_completion: int | None
    fluency: int | None
    factual_consistency: int | None
    field_accuracy: FieldAccuracy | None
    leaked_placeholder: bool
    final_response: str


def run_task(
    task: Task, doc: Document, model: TaskModel, judge: Judge
) -> list[TaskConditionRecord]:
    instruction = prompts.instruction_for(task.task_type, task.domain)
    records = []
    for condition in CONDITIONS:
        result = run_condition(model, condition, instruction, doc.text)
        verdict = judge.score(instruction, doc.text, result.final_response)
        field_accuracy = None
        if task.task_type == "extract_fields":
            field_accuracy = score_fields(result.final_response, task.gold_fields)
        records.append(
            TaskConditionRecord(
                task_id=task.id,
                domain=task.domain,
                task_type=task.task_type,
                condition=condition,
                task_completion=verdict.get("task_completion"),
                fluency=verdict.get("fluency"),
                factual_consistency=verdict.get("factual_consistency"),
                field_accuracy=field_accuracy,
                leaked_placeholder=result.had_leak or has_leak(result.final_response),
                final_response=result.final_response,
            )
        )
    return records


def run_all(
    tasks: list[Task], docs_by_id: dict[str, Document], model: TaskModel, judge: Judge
) -> list[TaskConditionRecord]:
    records: list[TaskConditionRecord] = []
    for task in tasks:
        records.extend(run_task(task, docs_by_id[task.doc_id], model, judge))
    return records
