from __future__ import annotations

import pytest
from maskflow_core import Mapping, PIIType, Span, mask_with_policy
from maskflow_core.mapping import MappingEntry
from maskflow_core.strategies import Strategy
from maskflow_evidence import (
    EventContext,
    action_for_strategy,
    events_from_mapping,
    events_from_spans,
)
from maskflow_evidence.schema import EvidenceSchemaError

CTX = EventContext(session_id="sess0000abcd", service="svc", environment="dev")


def _span(etype: str, start: int, end: int, score: float, recognizer: str) -> Span:
    return Span(
        start=start,
        end=end,
        entity_type=PIIType.register(etype),
        score=score,
        recognizer=recognizer,
        text="x" * (end - start),
    )


def test_events_from_spans_groups_by_type_recognizer_action() -> None:
    spans = [
        _span("EMAIL", 0, 5, 0.95, "pattern:EMAIL"),
        _span("EMAIL", 10, 15, 0.80, "pattern:EMAIL"),
        _span("PAN", 20, 30, 0.99, "pattern:PAN"),
    ]
    events = events_from_spans(spans, CTX)
    by_type = {e.entity_type: e for e in events}
    assert by_type["EMAIL"].count == 2
    assert by_type["EMAIL"].score == 0.80  # min of the group
    assert by_type["PAN"].count == 1
    assert all(e.action == "masked" for e in events)


def test_events_from_spans_dropped_become_passed() -> None:
    resolved = [_span("EMAIL", 0, 5, 0.95, "pattern:EMAIL")]
    dropped = [_span("PERSON_NAME", 10, 18, 0.30, "ner:PERSON")]
    events = events_from_spans(resolved, CTX, dropped=dropped)
    passed = [e for e in events if e.action == "passed"]
    assert len(passed) == 1
    assert passed[0].entity_type == "PERSON_NAME"


def test_events_from_spans_strategy_for_hook() -> None:
    spans = [_span("EMAIL", 0, 5, 0.95, "pattern:EMAIL")]
    events = events_from_spans(spans, CTX, strategy_for=lambda _t: "redacted")
    assert events[0].action == "redacted"


def test_action_for_strategy_mapping() -> None:
    assert action_for_strategy(Strategy.REPLACE) == "masked"
    assert action_for_strategy(Strategy.REDACT) == "redacted"
    assert action_for_strategy(Strategy.SURROGATE) == "surrogate"
    assert action_for_strategy(Strategy.HASH) == "masked"


def test_events_from_mapping_uses_entry_score_and_recognizer() -> None:
    result = mask_with_policy("email me at person@example.com please")
    events = events_from_mapping(result.mapping, CTX)
    assert len(events) == 1
    ev = events[0]
    assert ev.entity_type == "EMAIL"
    assert ev.recognizer == "pattern:EMAIL"
    assert 0.0 < ev.score <= 1.0


def test_events_from_mapping_only_tokens_filter() -> None:
    result = mask_with_policy("mail a@b.com and c@d.com")
    tokens = list(result.mapping)
    events = events_from_mapping(result.mapping, CTX, only_tokens=tokens[:1])
    assert events[0].count == 1


def test_events_from_mapping_tolerates_missing_metadata() -> None:
    entry = MappingEntry(
        token="<EMAIL_1>",
        entity_type=PIIType.register("EMAIL"),
        strategy=Strategy.REPLACE,
        reversible=True,
        original="a@b.com",
    )
    events = events_from_mapping(Mapping({"<EMAIL_1>": entry}), CTX)
    assert events[0].recognizer == "unknown"
    assert events[0].score == 1.0


def test_bad_context_rejected() -> None:
    spans = [_span("EMAIL", 0, 5, 0.95, "pattern:EMAIL")]
    bad = EventContext(session_id="user@example.com", service="svc", environment="dev")
    with pytest.raises(EvidenceSchemaError):
        events_from_spans(spans, bad)
