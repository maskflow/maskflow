"""apply_context_boost / apply_negative_context's keyword-proximity mechanism,
proven with synthetic registered types. Previously only exercised indirectly
through built-in types in the (now-relocated) accuracy suite; core needs
standalone coverage of its own engine behavior.
"""

import re

from maskflow_core.detection import detect
from maskflow_core.registry import register_pattern

AMBIGUOUS_RE = re.compile(r"\bAMBIG-\d{4}\b")

register_pattern(
    "AMBIGUOUS_MARKER",
    AMBIGUOUS_RE,
    0.4,
    context_keywords=("marker code",),
)

# Negative-context only: base clears the default threshold on its own, a
# nearby "example"/"sample" should pull it back under.
NEG_MARKER_RE = re.compile(r"\bNEG-\d{4}\b")

register_pattern(
    "NEG_MARKER",
    NEG_MARKER_RE,
    0.7,
    negative_context_keywords=("example", "sample"),
)

# Both halves on one type, plus a low base so the negative hit floors at 0.0.
BOTH_MARKER_RE = re.compile(r"\bBOTH-\d{4}\b")

register_pattern(
    "BOTH_MARKER",
    BOTH_MARKER_RE,
    0.2,
    context_keywords=("marker code",),
    negative_context_keywords=("dummy",),
)

# A checksum-validated type: the validator sets confidence to 0.95, and a
# nearby negative keyword must still be able to suppress it.
VALID_MARKER_RE = re.compile(r"\bVALID-(\d{4})\b")


def _validate_marker(value: str) -> float | None:
    return 0.95


register_pattern(
    "VALID_MARKER",
    VALID_MARKER_RE,
    0.4,
    validator=_validate_marker,
    negative_context_keywords=("test",),
)


def test_context_keyword_boosts_confidence_when_nearby() -> None:
    text = "Please note the marker code AMBIG-1234 below."
    spans = detect(text, min_confidence=0.0)

    span = next(s for s in spans if s.entity_type == "AMBIGUOUS_MARKER")
    assert span.score > 0.4


def test_missing_context_keyword_leaves_confidence_unboosted() -> None:
    text = "Nothing relevant here: AMBIG-5678 appears alone."
    spans = detect(text, min_confidence=0.0)

    span = next(s for s in spans if s.entity_type == "AMBIGUOUS_MARKER")
    assert span.score == 0.4


def test_explanation_records_pattern_hit_and_boosted_context_step() -> None:
    text = "Please note the marker code AMBIG-1234 below."
    spans = detect(text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "AMBIGUOUS_MARKER")

    assert any(
        step.rule == "pattern:AMBIGUOUS_MARKER" and step.outcome == "matched"
        for step in span.explanation
    )
    context_step = next(step for step in span.explanation if step.rule == "context")
    assert context_step.outcome == "boosted"
    assert context_step.delta > 0


def test_explanation_records_unboosted_context_step() -> None:
    text = "Nothing relevant here: AMBIG-5678 appears alone."
    spans = detect(text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "AMBIGUOUS_MARKER")

    context_step = next(step for step in span.explanation if step.rule == "context")
    assert context_step.outcome == "no_match"
    assert context_step.delta == 0


def test_negative_keyword_lowers_confidence_by_penalty() -> None:
    text = "Nothing relevant here: NEG-1000 appears alone."
    spans = detect(text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "NEG_MARKER")
    assert span.score == 0.7

    suppressed_text = "For example NEG-1000 is not a real value."
    spans = detect(suppressed_text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "NEG_MARKER")
    assert span.score == round(0.7 - 0.3, 2)


def test_negative_keyword_can_drop_span_below_threshold() -> None:
    # 0.7 base clears the 0.5 default; "sample" pulls it to 0.4, under the bar.
    text = "See the sample value NEG-2000 in the docs."
    spans = detect(text)
    assert not any(s.entity_type == "NEG_MARKER" for s in spans)


def test_negative_keyword_suppresses_checksum_validated_span() -> None:
    text = "This is just a test number VALID-1234, ignore it."
    spans = detect(text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "VALID_MARKER")
    assert span.validated is True
    assert span.score == round(0.95 - 0.3, 2)


def test_negative_penalty_floors_at_zero() -> None:
    # 0.2 base, positive boost is absent here, "dummy" would take it to -0.1.
    text = "Here is a dummy BOTH-1234 value."
    spans = detect(text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "BOTH_MARKER")
    assert span.score == 0.0


def test_positive_then_negative_both_apply_and_are_recorded() -> None:
    # "marker code" boosts 0.2 -> 0.6, then "dummy" suppresses 0.6 -> 0.3.
    text = "The dummy marker code BOTH-4321 is illustrative only."
    spans = detect(text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "BOTH_MARKER")
    assert span.score == round(0.2 + 0.4 - 0.3, 2)

    context_step = next(s for s in span.explanation if s.rule == "context")
    assert context_step.outcome == "boosted"
    negative_step = next(s for s in span.explanation if s.rule == "negative_context")
    assert negative_step.outcome == "suppressed"
    assert negative_step.delta == round(-0.3, 2)


def test_negative_context_step_no_match_when_keyword_absent() -> None:
    text = "Nothing relevant here: NEG-3000 appears alone."
    spans = detect(text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "NEG_MARKER")

    negative_step = next(s for s in span.explanation if s.rule == "negative_context")
    assert negative_step.outcome == "no_match"
    assert negative_step.delta == 0


def test_negative_context_step_not_configured_when_type_has_none() -> None:
    text = "Please note the marker code AMBIG-1234 below."
    spans = detect(text, min_confidence=0.0)
    span = next(s for s in spans if s.entity_type == "AMBIGUOUS_MARKER")

    negative_step = next(s for s in span.explanation if s.rule == "negative_context")
    assert negative_step.outcome == "not_configured"
