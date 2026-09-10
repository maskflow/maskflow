"""Coverage for the `run` subcommand's task selection -- no API, no network."""

from __future__ import annotations

from bench.indiapii.quality.__main__ import _select_tasks
from bench.indiapii.quality.tasks import Task

_TASKS = [
    Task(id=f"q-{i:03d}", doc_id=f"d{i}", domain="kyc_form", task_type=tt)
    for i, tt in enumerate(["summarize"] * 5 + ["draft_reply"] * 5 + ["extract_fields"] * 5)
]


def test_select_all_by_default() -> None:
    assert _select_tasks(_TASKS, None, None) == _TASKS


def test_limit_takes_the_first_n_in_file_order() -> None:
    picked = _select_tasks(_TASKS, 3, None)
    assert [t.id for t in picked] == ["q-000", "q-001", "q-002"]


def test_sample_per_type_spreads_across_task_types_and_overrides_limit() -> None:
    picked = _select_tasks(_TASKS, 99, per_type=2)
    from collections import Counter

    assert Counter(t.task_type for t in picked) == {
        "summarize": 2,
        "draft_reply": 2,
        "extract_fields": 2,
    }
