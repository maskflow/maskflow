from __future__ import annotations

from bench.indiapii.quality.report import aggregate, to_json_dict, to_markdown
from bench.indiapii.quality.runner import TaskConditionRecord
from bench.indiapii.quality.scoring import FieldAccuracy


def _record(
    task_id: str,
    task_type: str,
    condition: str,
    task_completion: int,
    fluency: int,
    factual_consistency: int,
    field_f1: float | None = None,
    leaked: bool = False,
) -> TaskConditionRecord:
    field_accuracy = FieldAccuracy(field_f1, field_f1, field_f1) if field_f1 is not None else None
    return TaskConditionRecord(
        task_id=task_id,
        domain="kyc_form",
        task_type=task_type,
        condition=condition,
        task_completion=task_completion,
        fluency=fluency,
        factual_consistency=factual_consistency,
        field_accuracy=field_accuracy,
        leaked_placeholder=leaked,
        final_response="a response",
    )


def test_aggregate_computes_paired_delta_vs_unmasked() -> None:
    records = [
        _record("t1", "summarize", "unmasked", 5, 5, 5),
        _record("t1", "summarize", "placeholder", 4, 5, 4),
        _record("t1", "summarize", "surrogate", 5, 5, 5),
        _record("t2", "summarize", "unmasked", 4, 4, 4),
        _record("t2", "summarize", "placeholder", 3, 4, 3),
        _record("t2", "summarize", "surrogate", 4, 4, 4),
    ]
    data = aggregate(records)
    summarize = data["task_types"]["summarize"]

    assert summarize["conditions"]["unmasked"]["task_completion"]["mean"] == 4.5
    placeholder_delta = summarize["deltas_vs_unmasked"]["placeholder"]["task_completion"]
    assert placeholder_delta["mean"] == -1.0
    surrogate_delta = summarize["deltas_vs_unmasked"]["surrogate"]["task_completion"]
    assert surrogate_delta["mean"] == 0.0


def test_aggregate_tracks_leak_rate() -> None:
    records = [
        _record("t1", "draft_reply", "placeholder", 5, 5, 5, leaked=True),
        _record("t2", "draft_reply", "placeholder", 5, 5, 5, leaked=False),
    ]
    data = aggregate(records)
    leak_rate = data["task_types"]["draft_reply"]["conditions"]["placeholder"]["leak_rate"]
    assert leak_rate == 0.5


def test_aggregate_includes_field_f1_only_for_extract_fields() -> None:
    records = [
        _record("t1", "extract_fields", "unmasked", 5, 5, 5, field_f1=1.0),
        _record("t1", "extract_fields", "placeholder", 5, 5, 5, field_f1=0.8),
        _record("t3", "summarize", "unmasked", 5, 5, 5),
    ]
    data = aggregate(records)
    assert "field_f1" in data["task_types"]["extract_fields"]["conditions"]["unmasked"]
    assert "field_f1" not in data["task_types"]["summarize"]["conditions"]["unmasked"]
    delta = data["task_types"]["extract_fields"]["deltas_vs_unmasked"]["placeholder"]["field_f1"]
    assert round(delta["mean"], 2) == -0.2


def test_missing_condition_for_a_task_is_skipped_not_crashed() -> None:
    records = [_record("t1", "summarize", "unmasked", 5, 5, 5)]
    data = aggregate(records)  # no placeholder/surrogate records for t1 at all
    delta = data["task_types"]["summarize"]["deltas_vs_unmasked"]["placeholder"]["task_completion"]
    assert delta["n"] == 0


def test_to_json_dict_and_markdown_do_not_crash_on_empty_records() -> None:
    data = to_json_dict([])
    assert data["num_records"] == 0
    markdown = to_markdown(data)
    assert "indiapii-quality-v1.0" in markdown
