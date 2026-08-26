"""maskflow_core.recognizer -- issue #21's pluggable Recognizer interface.

Covers: PatternRecognizer/GazetteerRecognizer/NlpRecognizer's analyze()
implementations against the same validator/context-boost/threshold behavior
_finish_match/detect_ner already had; Recognizer.register()'s idempotency
(needed because RecognizerRegistry-based discovery necessarily imports a
pack's module, which may already have registered eagerly -- see
maskflow_pack_intl/maskflow_pack_india's __init__.py); RecognizerRegistry's
lazy entry-point discovery; and this issue's explicit definition-of-done
property -- an AnalysisContext shared across several NER-dependent
recognizers triggers exactly one NLP parse.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import pytest
from maskflow_core.entities import PIIType, Span
from maskflow_core.recognizer import (
    AnalysisContext,
    GazetteerRecognizer,
    NlpRecognizer,
    PatternRecognizer,
    Recognizer,
    RecognizerRegistry,
)
from maskflow_core.registry import CUSTOM_RECOGNIZERS, PATTERNS


class _FakeEnt:
    def __init__(self, label: str, text: str, start: int, end: int) -> None:
        self.label_ = label
        self.text = text
        self.start_char = start
        self.end_char = end


class _FakeDoc:
    def __init__(self, ents: list[_FakeEnt]) -> None:
        self.ents = ents


class _CountingNlp:
    """A fake `nlp` callable (what `_get_nlp()`-style loaders return) that
    records how many times it was invoked -- the DoD test's probe."""

    def __init__(self, doc: _FakeDoc) -> None:
        self.doc = doc
        self.call_count = 0

    def __call__(self, text: str) -> _FakeDoc:
        self.call_count += 1
        return self.doc


# --------------------------------------------------------------------------
# PatternRecognizer
# --------------------------------------------------------------------------


def test_pattern_recognizer_analyze_matches_and_applies_validator() -> None:
    regex = re.compile(r"\bID-(\d{4})\b")
    recognizer = PatternRecognizer(
        "TEST_ID", regex, 0.5, validator=lambda v: 0.9 if v == "1234" else None
    )
    ctx = AnalysisContext(text="ref ID-1234 here")

    spans = list(recognizer.analyze("ref ID-1234 here", ctx))

    assert len(spans) == 1
    assert spans[0].entity_type == "TEST_ID"
    assert spans[0].score == 0.9
    assert spans[0].validated is True


def test_pattern_recognizer_analyze_drops_failed_validator() -> None:
    regex = re.compile(r"\bID-(\d{4})\b")
    recognizer = PatternRecognizer("TEST_ID2", regex, 0.5, validator=lambda v: None)
    ctx = AnalysisContext(text="ref ID-9999 here")

    assert list(recognizer.analyze("ref ID-9999 here", ctx)) == []


def test_pattern_recognizer_register_populates_patterns_dict() -> None:
    regex = re.compile(r"\bFOO\d+\b")
    recognizer = PatternRecognizer("TEST_FOO", regex, 0.7)

    registered_type = recognizer.register()

    assert registered_type in PATTERNS
    assert PATTERNS[registered_type] == [(regex, 0.7, None)]


def test_recognizer_register_is_idempotent() -> None:
    regex = re.compile(r"\bBAR\d+\b")
    recognizer = PatternRecognizer("TEST_BAR", regex, 0.6)

    first = recognizer.register()
    second = recognizer.register()

    assert first is second
    assert len(PATTERNS[first]) == 1


# --------------------------------------------------------------------------
# GazetteerRecognizer
# --------------------------------------------------------------------------


def test_gazetteer_recognizer_analyze_wraps_match_fn() -> None:
    def match_fn(text: str) -> Iterable[tuple[int, int, str, float]]:
        idx = text.find("Testville")
        if idx == -1:
            return
        yield idx, idx + len("Testville"), "Testville", 0.4

    recognizer = GazetteerRecognizer("TEST_PLACE", match_fn)
    ctx = AnalysisContext(text="I live in Testville today.")

    spans = list(recognizer.analyze("I live in Testville today.", ctx))

    assert len(spans) == 1
    assert spans[0].text == "Testville"
    assert spans[0].score == 0.4


def test_gazetteer_recognizer_register_populates_custom_recognizers_dict() -> None:
    def match_fn(text: str) -> Iterable[tuple[int, int, str, float]]:
        return []

    recognizer = GazetteerRecognizer("TEST_GAZ", match_fn)

    registered_type = recognizer.register()

    assert registered_type in CUSTOM_RECOGNIZERS
    assert CUSTOM_RECOGNIZERS[registered_type] == [(match_fn, None)]


# --------------------------------------------------------------------------
# NlpRecognizer + AnalysisContext.nlp_doc
# --------------------------------------------------------------------------


def test_nlp_recognizer_analyze_dispatches_matching_label() -> None:
    fake_doc = _FakeDoc([_FakeEnt("TEST_LABEL", "Testville", 10, 19)])
    recognizer = NlpRecognizer("TEST_LABEL", "TEST_RECOG_PLACE", 0.7)
    ctx = AnalysisContext(text="I live in Testville today.", nlp_loader=lambda: lambda t: fake_doc)

    spans = list(recognizer.analyze("I live in Testville today.", ctx))

    assert len(spans) == 1
    assert spans[0].entity_type == "TEST_RECOG_PLACE"
    assert spans[0].text == "Testville"


def test_nlp_recognizer_analyze_ignores_unmapped_labels() -> None:
    fake_doc = _FakeDoc([_FakeEnt("OTHER_LABEL", "Whatever", 0, 8)])
    recognizer = NlpRecognizer("TEST_LABEL", "TEST_PLACE2", 0.7)
    ctx = AnalysisContext(text="Whatever happens next.", nlp_loader=lambda: lambda t: fake_doc)

    assert list(recognizer.analyze("Whatever happens next.", ctx)) == []


def test_nlp_recognizer_analyze_drops_below_threshold() -> None:
    fake_doc = _FakeDoc([_FakeEnt("TEST_LOW_LABEL", "Something", 0, 9)])
    recognizer = NlpRecognizer("TEST_LOW_LABEL", "TEST_LOW2", 0.2, threshold=0.6)
    ctx = AnalysisContext(text="Something happened.", nlp_loader=lambda: lambda t: fake_doc)

    assert list(recognizer.analyze("Something happened.", ctx)) == []


def test_nlp_recognizer_agreement_boost_promotes_overlapping_candidate() -> None:
    fake_doc = _FakeDoc([_FakeEnt("TEST_AGREE_LABEL", "Priya", 0, 5)])
    recognizer = NlpRecognizer(
        "TEST_AGREE_LABEL", "TEST_AGREE", 0.3, threshold=0.5, agreement_boost=0.4
    )
    agreeing_span = Span(
        start=0,
        end=5,
        entity_type=PIIType.register("TEST_AGREE"),
        score=0.2,
        recognizer="x",
        text="Priya",
    )
    ctx = AnalysisContext(
        text="Priya called.",
        agreement_spans=[agreeing_span],
        nlp_loader=lambda: lambda t: fake_doc,
    )

    spans = list(recognizer.analyze("Priya called.", ctx))

    assert len(spans) == 1
    assert spans[0].score == pytest.approx(0.7)


def test_analysis_context_nlp_doc_is_computed_at_most_once() -> None:
    counting_nlp = _CountingNlp(_FakeDoc([]))
    ctx = AnalysisContext(text="some text", nlp_loader=lambda: counting_nlp)

    _ = ctx.nlp_doc
    _ = ctx.nlp_doc
    _ = ctx.nlp_doc

    assert counting_nlp.call_count == 1


def test_nlp_parses_exactly_once_across_several_ner_dependent_recognizers() -> None:
    """This issue's explicit definition-of-done property: however many
    NER-dependent recognizers share one AnalysisContext in one run, the
    underlying NLP parse happens exactly once."""
    fake_doc = _FakeDoc(
        [
            _FakeEnt("PERSON", "Priya Sharma", 0, 12),
            _FakeEnt("DATE", "12 March 1990", 20, 33),
        ]
    )
    counting_nlp = _CountingNlp(fake_doc)
    ctx = AnalysisContext(text="Priya Sharma born 12 March 1990", nlp_loader=lambda: counting_nlp)

    recognizers: list[Recognizer] = [
        NlpRecognizer("PERSON", "TEST_PERSON", 0.75),
        NlpRecognizer("DATE", "TEST_DOB", 0.3, threshold=0.2),
        NlpRecognizer("ORG", "TEST_ORG", 0.5),  # a third, unmatched recognizer
    ]

    all_spans = [span for r in recognizers for span in r.analyze(ctx.text, ctx)]

    assert counting_nlp.call_count == 1
    assert {s.entity_type for s in all_spans} == {"TEST_PERSON", "TEST_DOB"}


def test_analysis_context_nlp_doc_is_none_without_a_loader() -> None:
    ctx = AnalysisContext(text="no loader configured")

    assert ctx.nlp_doc is None


# --------------------------------------------------------------------------
# RecognizerRegistry -- lazy entry-point discovery
# --------------------------------------------------------------------------


class _FakeEntryPoint:
    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self.load_calls = 0

    def load(self) -> Any:
        self.load_calls += 1
        return self._factory


def _patch_entry_points(monkeypatch: pytest.MonkeyPatch, *eps: _FakeEntryPoint) -> None:
    def fake_entry_points(group: str) -> list[_FakeEntryPoint]:
        return list(eps) if group == "maskflow.recognizers" else []

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)


def test_registry_does_not_load_entry_points_until_recognizers_accessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ep = _FakeEntryPoint(lambda: [])
    _patch_entry_points(monkeypatch, ep)

    registry = RecognizerRegistry()
    assert ep.load_calls == 0  # constructing the registry must not import anything

    _ = registry.recognizers
    assert ep.load_calls == 1

    _ = registry.recognizers  # second access must not re-load
    assert ep.load_calls == 1


def test_registry_register_all_registers_discovered_recognizers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    regex = re.compile(r"\bBAZ\d+\b")
    recognizer = PatternRecognizer("TEST_BAZ", regex, 0.8)
    ep = _FakeEntryPoint(lambda: [recognizer])
    _patch_entry_points(monkeypatch, ep)

    registry = RecognizerRegistry()
    registered_types = registry.register_all()

    assert registered_types == [PIIType.register("TEST_BAZ")]
    assert PATTERNS[PIIType.register("TEST_BAZ")] == [(regex, 0.8, None)]


def test_registry_discovering_an_already_registered_recognizer_does_not_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Models the pack-intl/pack-india situation: the entry point's factory
    returns objects that were already registered by the module's own
    import-time side effect. register_all() must not double the pattern."""
    regex = re.compile(r"\bQUX\d+\b")
    recognizer = PatternRecognizer("TEST_QUX", regex, 0.5)
    recognizer.register()  # simulates the pack's own eager __init__.py registration
    ep = _FakeEntryPoint(lambda: [recognizer])
    _patch_entry_points(monkeypatch, ep)

    RecognizerRegistry().register_all()

    assert len(PATTERNS[PIIType.register("TEST_QUX")]) == 1
