"""detect(return_rejected=True) -- the opt-in path maskflow-cli's `explain`
command uses to surface below-threshold near misses.

Assertions filter on LOW_CONFIDENCE_MARKER specifically rather than
asserting whole-list equality: this suite runs standalone with no pack
installed, but also inside the full workspace test session where
maskflow-pack-intl's NER recognizers are registered against the same
global registry core uses -- spaCy can tag unrelated substrings of the test
text, so a blanket `accepted == []` would be session-order-dependent.
"""

from __future__ import annotations

import re

from maskflow_core.detection import detect
from maskflow_core.registry import register_pattern

LOW_CONFIDENCE_RE = re.compile(r"\bWEAK-\d{4}\b")

register_pattern("LOW_CONFIDENCE_MARKER", LOW_CONFIDENCE_RE, 0.3)


def test_default_call_still_returns_a_plain_list() -> None:
    spans = detect("see WEAK-1234 here", min_confidence=0.5)
    assert isinstance(spans, list)
    assert all(hasattr(s, "start") for s in spans)


def test_return_rejected_true_returns_accepted_and_rejected_tuple() -> None:
    accepted, rejected = detect("see WEAK-1234 here", min_confidence=0.5, return_rejected=True)

    assert not any(s.entity_type == "LOW_CONFIDENCE_MARKER" for s in accepted)
    marker_rejections = [s for s in rejected if s.entity_type == "LOW_CONFIDENCE_MARKER"]
    assert len(marker_rejections) == 1
    assert marker_rejections[0].score == 0.3


def test_return_rejected_accepted_list_matches_default_call() -> None:
    text = "see WEAK-1234 here"
    plain = detect(text, min_confidence=0.0)
    accepted, _rejected = detect(text, min_confidence=0.0, return_rejected=True)

    assert [(s.start, s.end, s.entity_type) for s in accepted] == [
        (s.start, s.end, s.entity_type) for s in plain
    ]


def test_rejected_span_explanation_ends_with_threshold_dropped_step() -> None:
    _accepted, rejected = detect("see WEAK-1234 here", min_confidence=0.5, return_rejected=True)
    marker_rejection = next(s for s in rejected if s.entity_type == "LOW_CONFIDENCE_MARKER")

    step = marker_rejection.explanation[-1]
    assert step.rule == "threshold"
    assert step.outcome == "dropped"


def test_exclusions_are_applied_to_both_accepted_and_rejected() -> None:
    text = "see WEAK-1234 here"
    accepted, rejected = detect(
        text, min_confidence=0.5, return_rejected=True, exclusion_values=frozenset({"WEAK-1234"})
    )
    assert not any(s.text == "WEAK-1234" for s in accepted)
    assert not any(s.text == "WEAK-1234" for s in rejected)
