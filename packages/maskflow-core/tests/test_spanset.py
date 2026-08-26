"""SpanSet.resolve() -- the central overlap-resolution algorithm every
recognizer (regex + NER) feeds into. Property tests use Hypothesis to probe
the algorithm broadly; the two named regressions pin down specific shapes
called out in the design doc. All synthetic registered types, like the rest
of core's test suite, so these hold with no pack installed at all.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType, Span
from maskflow_core.registry import PATTERNS, register_pattern
from maskflow_core.spanset import OverlapPolicy, ResolveConfig, resolve, resolve_verbose

TEXT = "the quick brown fox jumps over the lazy dog while a cat sleeps nearby"

TYPE_A = PIIType.register("PROP_TEST_TYPE_A")
TYPE_B = PIIType.register("PROP_TEST_TYPE_B")

DEFAULT_CONFIG = ResolveConfig(default_threshold=0.0)


@st.composite
def _span(draw: st.DrawFn, entity_types: tuple[PIIType, ...] = (TYPE_A, TYPE_B)) -> Span:
    start = draw(st.integers(min_value=0, max_value=len(TEXT) - 2))
    end = draw(st.integers(min_value=start + 1, max_value=len(TEXT)))
    entity_type = draw(st.sampled_from(entity_types))
    score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    validated = draw(st.booleans())
    return Span(
        start=start,
        end=end,
        entity_type=entity_type,
        score=score,
        recognizer="prop-test",
        text=TEXT[start:end],
        validated=validated,
    )


def _key(spans: list[Span]) -> list[tuple[int, int, PIIType, float, bool]]:
    return [(s.start, s.end, s.entity_type, round(s.score, 6), s.validated) for s in spans]


@given(st.lists(_span(), min_size=0, max_size=12))
@settings(max_examples=200)
def test_no_overlap(candidates: list[Span]) -> None:
    result = resolve(candidates, TEXT, DEFAULT_CONFIG)
    for a, b in zip(result, result[1:], strict=False):
        assert a.end <= b.start, f"Overlapping resolved spans: {a} and {b}"


@given(st.lists(_span(), min_size=0, max_size=12))
@settings(max_examples=200)
def test_deterministic(candidates: list[Span]) -> None:
    first = resolve(candidates, TEXT, DEFAULT_CONFIG)
    second = resolve(list(candidates), TEXT, DEFAULT_CONFIG)
    assert _key(first) == _key(second)


@given(st.lists(_span(), min_size=0, max_size=12))
@settings(max_examples=200)
def test_idempotent(candidates: list[Span]) -> None:
    once = resolve(candidates, TEXT, DEFAULT_CONFIG)
    twice = resolve(once, TEXT, DEFAULT_CONFIG)
    assert _key(once) == _key(twice)


@given(st.data())
@settings(max_examples=200)
def test_validated_survives(data: st.DataObject) -> None:
    """A validated span is never dropped in favor of an overlapping
    unvalidated one, regardless of score/length/overlap policy -- the one
    invariant that must hold no matter how the two spans otherwise differ."""
    start = data.draw(st.integers(min_value=0, max_value=len(TEXT) - 5))
    end = data.draw(st.integers(min_value=start + 1, max_value=min(start + 5, len(TEXT))))
    validated_span = Span(
        start=start,
        end=end,
        entity_type=TYPE_A,
        score=0.5,
        recognizer="prop-test",
        text=TEXT[start:end],
        validated=True,
    )

    # An unvalidated span drawn to always overlap validated_span's range,
    # with the maximum possible score/length advantage.
    other_start = data.draw(st.integers(min_value=max(0, start - 3), max_value=end - 1))
    other_end = data.draw(
        st.integers(min_value=max(other_start + 1, start + 1), max_value=min(len(TEXT), end + 3))
    )
    unvalidated_span = Span(
        start=other_start,
        end=other_end,
        entity_type=TYPE_B,
        score=1.0,
        recognizer="prop-test",
        text=TEXT[other_start:other_end],
        validated=False,
    )

    policy = data.draw(st.sampled_from(list(OverlapPolicy)))
    config = ResolveConfig(default_threshold=0.0, default_overlap_policy=policy)

    result = resolve([validated_span, unvalidated_span], TEXT, config)
    assert any(s.validated and s.start == start and s.end == end for s in result)


def test_nested_specific_span_wins_over_a_longer_unvalidated_run() -> None:
    """Named regression (a): a checksum-validated span nested inside a wider,
    unvalidated run must resolve to exactly the nested span -- not the wider
    run, not nothing. This is the plain validated-survives invariant (default
    STRICT policy is enough -- the validated span is processed first and the
    wider unvalidated one simply loses to it as a CROSSING/CONTAINS conflict).
    Modeled directly on SpanSet (not through regex) since it's the
    containment algorithm being pinned down, independent of any particular
    pack's pattern accidentally producing this shape."""
    text = "ref 91234567890123 on file"
    outer_start, outer_end = (
        text.index("91234567890123"),
        text.index("91234567890123") + len("91234567890123"),
    )
    inner_start, inner_end = outer_start + 1, outer_start + 13  # the embedded 12-digit run

    outer = Span(
        start=outer_start,
        end=outer_end,
        entity_type=TYPE_A,
        score=0.4,
        recognizer="pattern:GENERIC_DIGIT_RUN",
        text=text[outer_start:outer_end],
        validated=False,
    )
    inner = Span(
        start=inner_start,
        end=inner_end,
        entity_type=TYPE_B,
        score=0.4,
        recognizer="pattern:SPECIFIC_ID",
        text=text[inner_start:inner_end],
        validated=True,
    )

    result = resolve([outer, inner], text, DEFAULT_CONFIG)

    assert len(result) == 1
    assert (result[0].start, result[0].end) == (inner_start, inner_end)
    assert result[0].text == text[inner_start:inner_end]


def test_contained_policy_prefers_the_more_specific_span_when_validation_is_equal() -> None:
    """CONTAINED overlap policy: when two overlapping spans of the same
    validation status nest, the smaller/more specific one wins (the inverse
    of the default length-desc tiebreak) -- e.g. a specific structural match
    nested inside a generic catch-all match, neither of them validated."""
    text = "token: abc123XYZ789 please rotate"
    outer_start, outer_end = (
        text.index("abc123XYZ789"),
        text.index("abc123XYZ789") + len("abc123XYZ789"),
    )
    inner_start, inner_end = outer_start + 3, outer_start + 9  # "123XYZ", the specific part

    outer = Span(
        start=outer_start,
        end=outer_end,
        entity_type=TYPE_A,
        score=0.6,
        recognizer="pattern:GENERIC_SECRET",
        text=text[outer_start:outer_end],
        validated=False,
    )
    inner = Span(
        start=inner_start,
        end=inner_end,
        entity_type=TYPE_B,
        score=0.6,
        recognizer="pattern:SPECIFIC_TOKEN",
        text=text[inner_start:inner_end],
        validated=False,
    )

    config = ResolveConfig(
        default_threshold=0.0,
        per_entity_overlap_policy={TYPE_A: OverlapPolicy.CONTAINED},
    )
    result = resolve([outer, inner], text, config)

    assert len(result) == 1
    assert (result[0].start, result[0].end) == (inner_start, inner_end)
    assert any(
        step.rule == "overlap:contained" and step.outcome == "preferred"
        for step in result[0].explanation
    )


def test_merge_policy_joins_adjacent_same_type_spans() -> None:
    """MERGE overlap policy: two disjoint same-type spans separated by a
    single space join into one span covering both, e.g. a first-name and a
    last-name span recognized separately."""
    text = "Please contact Jane Doe about the invoice."
    first_start, first_end = text.index("Jane"), text.index("Jane") + len("Jane")
    last_start, last_end = text.index("Doe"), text.index("Doe") + len("Doe")

    first = Span(
        start=first_start,
        end=first_end,
        entity_type=TYPE_A,
        score=0.7,
        recognizer="ner:PERSON_FIRST",
        text=text[first_start:first_end],
    )
    last = Span(
        start=last_start,
        end=last_end,
        entity_type=TYPE_A,
        score=0.7,
        recognizer="ner:PERSON_LAST",
        text=text[last_start:last_end],
    )

    config = ResolveConfig(
        default_threshold=0.0,
        per_entity_overlap_policy={TYPE_A: OverlapPolicy.MERGE},
    )
    result = resolve([first, last], text, config)

    assert len(result) == 1
    assert (result[0].start, result[0].end) == (first_start, last_end)
    assert result[0].text == "Jane Doe"


EMAIL_LIKE_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
UPI_LIKE_RE = re.compile(r"\b[A-Za-z0-9.\-]{2,}@[A-Za-z][A-Za-z0-9]{1,}\b")


@pytest.fixture
def _email_and_upi_patterns() -> Iterator[None]:
    """Registers SYN_EMAIL/SYN_UPI_HANDLE for just this test, then removes
    them again -- unlike the module-level registrations elsewhere in this
    suite, EMAIL_LIKE_RE is deliberately identical to pack-intl's real
    EMAIL_RE, so leaving it registered for the rest of the (shared,
    workspace-wide) pytest session would give every other real email a
    competing SYN_EMAIL candidate at the same span."""
    email_type = register_pattern("SYN_EMAIL", EMAIL_LIKE_RE, 0.95)
    upi_type = register_pattern("SYN_UPI_HANDLE", UPI_LIKE_RE, 0.7)
    yield
    PATTERNS.pop(email_type, None)
    PATTERNS.pop(upi_type, None)


def test_email_and_upi_shaped_handle_resolve_independently(
    _email_and_upi_patterns: None,
) -> None:
    """Named regression (b): a real email and a UPI-shaped (user@bank) handle
    in the same text must each resolve to their own correct span -- distinct,
    non-overlapping, and neither absorbing the other. Checked by exact
    (start, end) rather than entity_type name: EMAIL_LIKE_RE is deliberately
    shaped just like a real email, so if a pack that also registers a real
    EMAIL recognizer happens to share this test session, both compete for
    the identical span and resolve() correctly keeps exactly one -- which
    type wins that tie isn't what this test is pinning down."""
    text = "Email me at alice@example.com or pay me at alice@paytm for the split."
    spans = detect(text, min_confidence=0.0)

    email_value = "alice@example.com"
    email_start = text.index(email_value)
    email_end = email_start + len(email_value)
    email_matches = [s for s in spans if (s.start, s.end) == (email_start, email_end)]

    upi_value = "alice@paytm"
    upi_start = text.index(upi_value)
    upi_end = upi_start + len(upi_value)
    upi_matches = [s for s in spans if (s.start, s.end) == (upi_start, upi_end)]

    assert len(email_matches) == 1
    assert email_matches[0].text == email_value

    assert len(upi_matches) == 1
    assert upi_matches[0].text == upi_value

    assert email_matches[0].entity_type != upi_matches[0].entity_type

    for a, b in zip(spans, spans[1:], strict=False):
        assert a.end <= b.start


def test_resolve_verbose_accepted_matches_plain_resolve() -> None:
    text = "the quick brown fox"
    low = Span(start=4, end=9, entity_type=TYPE_A, score=0.2, recognizer="prop-test", text="quick")
    high = Span(
        start=10, end=15, entity_type=TYPE_B, score=0.9, recognizer="prop-test", text="brown"
    )
    config = ResolveConfig(default_threshold=0.5)

    accepted, rejected = resolve_verbose([low, high], text, config)

    assert accepted == resolve([low, high], text, config)
    assert accepted == [high]
    assert rejected == [low]


def test_resolve_verbose_stamps_rejected_spans_with_threshold_step() -> None:
    text = "the quick brown fox"
    low = Span(start=4, end=9, entity_type=TYPE_A, score=0.2, recognizer="prop-test", text="quick")
    config = ResolveConfig(default_threshold=0.5)

    _, rejected = resolve_verbose([low], text, config)

    assert len(rejected) == 1
    step = rejected[0].explanation[-1]
    assert step.rule == "threshold"
    assert step.outcome == "dropped"


def test_resolve_verbose_does_not_reject_spans_that_only_lost_to_overlap() -> None:
    """A span dropped for losing an overlap conflict (not for scoring below
    threshold) must not show up in `rejected` -- only the threshold cut
    counts as a near miss."""
    text = "the quick brown fox"
    winner = Span(
        start=4, end=9, entity_type=TYPE_A, score=0.9, recognizer="prop-test", text="quick"
    )
    loser = Span(
        start=4, end=9, entity_type=TYPE_B, score=0.8, recognizer="prop-test", text="quick"
    )
    config = ResolveConfig(default_threshold=0.0)

    accepted, rejected = resolve_verbose([winner, loser], text, config)

    assert accepted == [winner]
    assert rejected == []
