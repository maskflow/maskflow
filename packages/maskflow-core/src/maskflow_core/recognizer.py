"""Pluggable recognizer interface (issue #21): the `Recognizer` ABC third
parties implement, `AnalysisContext` (the per-`detect()`-call shared state,
including a lazily computed and memoised NLP doc so any number of
NER-dependent recognizers sharing one context trigger exactly one parse),
three base helpers covering the three match strategies core already
supports (`PatternRecognizer`, `GazetteerRecognizer`, `NlpRecognizer`), and
`RecognizerRegistry` (entry-point discovery, group "maskflow.recognizers").

Design note -- how this coexists with the pre-existing manual registration
path (registry.PATTERNS/CUSTOM_RECOGNIZERS/NER_RECOGNIZERS,
register_pattern()/register_custom_recognizer()/register_ner_recognizer()):
detection.py's resolution pipeline (detect()/detect_ner()) reads only those
dicts and is UNCHANGED by this module. Every recognizer class here has a
`register()` method whose job is to populate those same dicts -- so once a
Recognizer is registered, it flows through the existing, proven pipeline
exactly like a hand-called register_pattern() would. This is what makes
"add an entity type without touching core" real: RecognizerRegistry
discovers a pack's Recognizer objects and calls register() on each; core's
detection code never has to know the discovery mechanism changed.
`analyze(text, ctx)` is the ABC's own interface -- exercised directly by
PatternRecognizer/GazetteerRecognizer/NlpRecognizer's implementations
(unit-testable in isolation, e.g. the "spaCy parses exactly once" property)
and available to a fully custom Recognizer subclass, which can rely on the
base class's default register() (wraps analyze() as a CUSTOM_RECOGNIZERS
match function) instead of writing its own.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from .context import apply_context_boost
from .entities import ExplanationStep, PIIType, Span
from .registry import (
    CustomMatchFn,
    Validator,
    register_custom_recognizer,
    register_ner_recognizer,
    register_pattern,
)


def _finish_match(
    text: str,
    pii_type: PIIType,
    start: int,
    end: int,
    value: str,
    base_confidence: float,
    validator: Validator | None,
    recognizer: str,
) -> Span | None:
    """Shared by every non-NLP recognizer kind: run the optional checksum
    validator, apply the context-keyword boost, and build the resulting
    Span -- or return None if a validator rejected the match outright.
    Moved here from detection.py (same body, not reimplemented) so
    PatternRecognizer/GazetteerRecognizer.analyze() and detection.py's
    dict-based pattern pass share one implementation."""
    explanation: list[ExplanationStep] = [ExplanationStep(rule=recognizer, outcome="matched")]

    confidence = base_confidence
    validated = False
    if validator is not None:
        adjusted = validator(value)
        if adjusted is None:
            return None
        explanation.append(
            ExplanationStep(
                rule="checksum", outcome="passed", delta=round(adjusted - confidence, 2)
            )
        )
        confidence = adjusted
        validated = True

    confidence, context_step = apply_context_boost(text, start, end, pii_type, confidence)
    explanation.append(context_step)

    return Span(
        start=start,
        end=end,
        entity_type=pii_type,
        score=round(confidence, 2),
        recognizer=recognizer,
        text=value,
        validated=validated,
        explanation=explanation,
    )


def _scan_pattern(
    text: str,
    pii_type: PIIType,
    regex: re.Pattern[str],
    base_confidence: float,
    validator: Validator | None,
) -> Iterator[Span]:
    for match in regex.finditer(text):
        if match.re.groups:
            start, end = match.span(1)
            value = match.group(1)
        else:
            start, end = match.span(0)
            value = match.group(0)

        span = _finish_match(
            text, pii_type, start, end, value, base_confidence, validator, f"pattern:{pii_type}"
        )
        if span is not None:
            yield span


def _scan_custom(
    text: str,
    pii_type: PIIType,
    match_fn: CustomMatchFn,
    validator: Validator | None,
) -> Iterator[Span]:
    for start, end, value, base_confidence in match_fn(text):
        span = _finish_match(
            text, pii_type, start, end, value, base_confidence, validator, f"custom:{pii_type}"
        )
        if span is not None:
            yield span


@dataclass
class AnalysisContext:
    """Per-`detect()`-call state handed to every `Recognizer.analyze()`.

    `nlp_doc` is a lazily computed property, not a plain field: parsing is
    the single most expensive step in a run, and most recognizers (every
    pattern/gazetteer one) never touch it. It is computed at most once per
    AnalysisContext instance -- however many NlpRecognizer instances read
    it while analyzing the same context, the underlying parse happens
    exactly once. Deliberately per-instance rather than a process-level
    cache: that is what lets each `detect()` call see its own text without
    one run's parse leaking into another's.
    """

    text: str
    language: str = "en"
    disabled_types: frozenset[PIIType] = field(default_factory=frozenset)
    # Every pattern/custom-recognizer candidate from this run (not just the
    # ones that cleared their own threshold) -- an NlpRecognizer with
    # agreement_boost > 0 uses this as its "does an independent L1/L2 method
    # agree" signal. See NerMapping.agreement_boost in registry.py.
    agreement_spans: Sequence[Span] = ()
    config: dict[str, Any] = field(default_factory=dict)
    nlp_loader: Callable[[], Any] | None = field(default=None, repr=False)
    _nlp_doc: Any = field(default=None, repr=False, init=False)
    _nlp_doc_computed: bool = field(default=False, repr=False, init=False)

    @property
    def nlp_doc(self) -> Any:
        if not self._nlp_doc_computed:
            nlp = self.nlp_loader() if self.nlp_loader is not None else None
            self._nlp_doc = nlp(self.text) if nlp is not None else None
            self._nlp_doc_computed = True
        return self._nlp_doc


class Recognizer(ABC):
    """Base interface every recognizer -- built-in or third-party --
    implements. `entity_type`/`supported_languages`/`default_threshold` are
    metadata a registry can inspect without running analyze(); analyze()
    does the actual work against one document's worth of context.
    """

    entity_type: str
    supported_languages: tuple[str, ...] = ("en",)
    default_threshold: float = 0.0
    _registered_type: PIIType | None = None

    @abstractmethod
    def analyze(self, text: str, ctx: AnalysisContext) -> Iterable[Span]: ...

    def register(self) -> PIIType:
        """Register this recognizer into core's PATTERNS/CUSTOM_RECOGNIZERS/
        NER_RECOGNIZERS dicts. Idempotent per instance -- a second call
        returns the cached PIIType without registering again, so the same
        Recognizer object can safely be registered once eagerly (e.g. a
        pack's __init__.py, for import-time-side-effect backward
        compatibility) and again via RecognizerRegistry-based discovery
        (which necessarily imports that same module to load its entry
        point) without double-counting a pattern. Subclasses implement
        `_do_register()`, not this method.
        """
        if self._registered_type is None:
            self._registered_type = self._do_register()
        return self._registered_type

    def _do_register(self) -> PIIType:
        """Default registration: wraps analyze() as a CUSTOM_RECOGNIZERS
        match function so ANY Recognizer subclass -- however it implements
        analyze() -- can be plugged into the existing detect() pipeline
        with no core changes. PatternRecognizer/GazetteerRecognizer/
        NlpRecognizer override this with a more precise native mapping; a
        fully custom Recognizer subclass can rely on this default instead
        of writing its own.

        Caution for a custom analyze() that reads ctx.nlp_doc: this default
        builds a fresh AnalysisContext (and therefore a fresh parse) on
        every detect() call, independent of the built-in NER pass's own
        parse -- subclass NlpRecognizer instead if you need to share it.
        """
        registered_type = PIIType.register(self.entity_type)

        def _match_fn(text: str) -> Iterable[tuple[int, int, str, float]]:
            ctx = AnalysisContext(text=text)
            for span in self.analyze(text, ctx):
                yield span.start, span.end, span.text, span.score

        return register_custom_recognizer(registered_type, _match_fn)


class PatternRecognizer(Recognizer):
    """A single (regex, base_confidence, optional validator) rule -- the
    declarative equivalent of one register_pattern() call."""

    def __init__(
        self,
        pii_type: str,
        regex: re.Pattern[str],
        base_confidence: float,
        validator: Validator | None = None,
        context_keywords: tuple[str, ...] | None = None,
        default_threshold: float = 0.0,
    ) -> None:
        self.entity_type = pii_type
        self.regex = regex
        self.base_confidence = base_confidence
        self.validator = validator
        self.context_keywords = context_keywords
        self.default_threshold = default_threshold

    def analyze(self, text: str, ctx: AnalysisContext) -> Iterable[Span]:
        registered_type = PIIType.register(self.entity_type)
        yield from _scan_pattern(
            text, registered_type, self.regex, self.base_confidence, self.validator
        )

    def _do_register(self) -> PIIType:
        return register_pattern(
            self.entity_type,
            self.regex,
            self.base_confidence,
            self.validator,
            self.context_keywords,
        )


class GazetteerRecognizer(Recognizer):
    """A non-regex match source (e.g. an Aho-Corasick automaton scan) --
    the declarative equivalent of one register_custom_recognizer() call."""

    def __init__(
        self,
        pii_type: str,
        match_fn: CustomMatchFn,
        validator: Validator | None = None,
        context_keywords: tuple[str, ...] | None = None,
        default_threshold: float = 0.0,
    ) -> None:
        self.entity_type = pii_type
        self.match_fn = match_fn
        self.validator = validator
        self.context_keywords = context_keywords
        self.default_threshold = default_threshold

    def analyze(self, text: str, ctx: AnalysisContext) -> Iterable[Span]:
        registered_type = PIIType.register(self.entity_type)
        yield from _scan_custom(text, registered_type, self.match_fn, self.validator)

    def _do_register(self) -> PIIType:
        return register_custom_recognizer(
            self.entity_type, self.match_fn, self.validator, self.context_keywords
        )


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


class NlpRecognizer(Recognizer):
    """One spaCy entity label -> PIIType mapping -- the declarative
    equivalent of one register_ner_recognizer() call. analyze() reads
    `ctx.nlp_doc` (lazily parsed, memoised on ctx) rather than parsing its
    own -- this is the piece that makes "spaCy runs exactly once no matter
    how many NER-dependent recognizers share a run" a property of the
    shared AnalysisContext rather than of any one recognizer.

    Kept independent of ner.py's detect_ner() by design: detect_ner() is
    the pipeline's proven, unchanged live NER pass (still dict-driven, see
    module docstring); this is the equivalent logic exposed as a real,
    directly testable Recognizer for the pluggable interface and for third
    parties who discover recognizers via RecognizerRegistry.
    """

    def __init__(
        self,
        spacy_label: str,
        pii_type: str,
        base_confidence: float,
        threshold: float = 0.0,
        context_keywords: tuple[str, ...] | None = None,
        agreement_boost: float = 0.0,
    ) -> None:
        self.spacy_label = spacy_label
        self.entity_type = pii_type
        self.base_confidence = base_confidence
        self.default_threshold = threshold
        self.context_keywords = context_keywords
        self.agreement_boost = agreement_boost

    def analyze(self, text: str, ctx: AnalysisContext) -> Iterable[Span]:
        doc = ctx.nlp_doc
        if doc is None:
            return

        registered_type = PIIType.register(self.entity_type)

        for ent in doc.ents:
            if ent.label_ != self.spacy_label:
                continue
            if registered_type in ctx.disabled_types:
                continue

            explanation: list[ExplanationStep] = [
                ExplanationStep(rule=f"ner:{ent.label_}", outcome="matched")
            ]

            confidence = self.base_confidence
            if self.agreement_boost > 0:
                agrees = any(
                    cand.entity_type == registered_type
                    and _overlaps(ent.start_char, ent.end_char, cand.start, cand.end)
                    for cand in ctx.agreement_spans
                )
                if agrees:
                    confidence = min(1.0, confidence + self.agreement_boost)
                    explanation.append(
                        ExplanationStep(
                            rule="agreement",
                            outcome="matched",
                            delta=self.agreement_boost,
                            detail="overlaps an L1/L2 candidate of the same type",
                        )
                    )
                else:
                    explanation.append(
                        ExplanationStep(
                            rule="agreement", outcome="no_match", detail="no L1/L2 overlap"
                        )
                    )

            confidence, context_step = apply_context_boost(
                text, ent.start_char, ent.end_char, registered_type, confidence
            )
            explanation.append(context_step)

            if confidence >= self.default_threshold:
                yield Span(
                    start=ent.start_char,
                    end=ent.end_char,
                    entity_type=registered_type,
                    score=confidence,
                    recognizer=f"ner:{ent.label_}",
                    text=ent.text,
                    explanation=explanation,
                )

    def _do_register(self) -> PIIType:
        return register_ner_recognizer(
            self.spacy_label,
            self.entity_type,
            self.base_confidence,
            self.default_threshold,
            self.context_keywords,
            self.agreement_boost,
        )


RecognizerFactory = Callable[[], Iterable[Recognizer]]


class RecognizerRegistry:
    """Discovers Recognizer objects via the "maskflow.recognizers"
    entry-point group and registers them into core's existing
    PATTERNS/CUSTOM_RECOGNIZERS/NER_RECOGNIZERS dicts.

    Discovery is lazy relative to importing maskflow_core: enumerating
    entry points (`importlib.metadata.entry_points()`) never imports the
    target module, only `.load()` does -- and `.load()` only runs the
    first time `.recognizers`/`.register_all()` is actually accessed, not
    at RecognizerRegistry() construction time. A pack's heavy dependencies
    (spaCy, pyahocorasick, ...) therefore never import just because the
    pack is pip-installed; they import once this process actually asks the
    registry to discover recognizers.

    This is an additive, opt-in discovery mechanism -- nothing in
    detect()'s default call path constructs or consults a RecognizerRegistry
    automatically, so installing a pack that ships a "maskflow.recognizers"
    entry point has no effect unless something explicitly calls
    RecognizerRegistry().register_all() (or discovers it another way). This
    is deliberate: it is a new, additional way for a pack to plug in,
    alongside (not replacing) the existing register-at-import-time path
    maskflow-pack-intl/maskflow-pack-india's own __init__.py still uses for
    their proven, unchanged bundled-pack activation route. Both paths are
    safe to use together for the same pack in the same process --
    Recognizer.register() is idempotent per instance, and loading a pack's
    entry point necessarily imports (and therefore already eagerly
    registers) that pack's module, so register_all() re-registering the
    same already-registered objects is a no-op, not a duplicate.
    """

    _GROUP = "maskflow.recognizers"

    def __init__(self) -> None:
        self._entry_points: list[Any] | None = None
        self._recognizers: list[Recognizer] | None = None

    def _discover_entry_points(self) -> list[Any]:
        if self._entry_points is None:
            from importlib.metadata import entry_points

            self._entry_points = list(entry_points(group=self._GROUP))
        return self._entry_points

    @property
    def recognizers(self) -> list[Recognizer]:
        if self._recognizers is None:
            collected: list[Recognizer] = []
            for ep in self._discover_entry_points():
                factory: RecognizerFactory = ep.load()
                collected.extend(factory())
            self._recognizers = collected
        return self._recognizers

    def register_all(self) -> list[PIIType]:
        """Register every discovered Recognizer, returning the PIIType
        each one's register() call resolved to, in discovery order."""
        return [recognizer.register() for recognizer in self.recognizers]


__all__ = [
    "AnalysisContext",
    "GazetteerRecognizer",
    "NlpRecognizer",
    "PatternRecognizer",
    "Recognizer",
    "RecognizerFactory",
    "RecognizerRegistry",
]
