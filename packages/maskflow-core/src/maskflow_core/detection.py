"""Orchestrates the regex, tier-0 excision, and NER passes into one resolved,
non-overlapping Span list. See CLAUDE.md 'Design decisions' #1-2 and
spanset.py for the resolution algorithm itself.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Literal, overload

from .context import apply_context_boost
from .entities import ExplanationStep, PIIType, Span
from .ner import detect_ner
from .registry import PATTERNS, Validator
from .spanset import ResolveConfig, SpanSet

DEFAULT_MIN_CONFIDENCE = 0.5

# A single fixed filler character, repeated to preserve length/char offsets,
# used to blank out tier-0 (already-resolved, high-confidence) regions before
# the NER pass runs. Non-word so spaCy's tokenizer never mistakes a run of it
# for a name/number; length-preserving so every downstream NER char offset
# still lines up with the original text.
_EXCISION_CHAR = "█"

# A defensive cap on how much text an exclusion pattern is asked to match
# against -- independent of whatever safety-checked the pattern at config
# validation time (maskflow_core.config.redos), since that check runs
# against the pattern, not against arbitrary future input. Mirrors
# config.redos.MAX_MATCH_LEN's spirit but is not imported from there:
# detection.py must stay config-agnostic (config depends on detection's
# types, never the reverse).
_MAX_EXCLUSION_MATCH_LEN = 10_000


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

        explanation: list[ExplanationStep] = [
            ExplanationStep(rule=f"pattern:{pii_type}", outcome="matched")
        ]

        confidence = base_confidence
        validated = False
        if validator is not None:
            adjusted = validator(value)
            if adjusted is None:
                # No Span is emitted for a checksum failure -- there is
                # nothing to attach this outcome to, and nothing for
                # detect(return_rejected=True) to surface as a near miss.
                continue
            explanation.append(
                ExplanationStep(
                    rule="checksum", outcome="passed", delta=round(adjusted - confidence, 2)
                )
            )
            confidence = adjusted
            validated = True

        confidence, context_step = apply_context_boost(text, start, end, pii_type, confidence)
        explanation.append(context_step)

        yield Span(
            start=start,
            end=end,
            entity_type=pii_type,
            score=round(confidence, 2),
            recognizer=f"pattern:{pii_type}",
            text=value,
            validated=validated,
            explanation=explanation,
        )


def _pattern_pass(
    text: str,
    disabled_types: frozenset[PIIType] = frozenset(),
    extra_patterns: Sequence[tuple[PIIType, re.Pattern[str], float]] = (),
) -> list[Span]:
    candidates: list[Span] = []

    for pii_type, rules in PATTERNS.items():
        if pii_type in disabled_types:
            continue
        for regex, base_confidence, validator in rules:
            candidates.extend(_scan_pattern(text, pii_type, regex, base_confidence, validator))

    # extra_patterns (from .maskflowrc's [custom.*]) are scanned the same
    # way as registered patterns, just with no validator -- they're already
    # ReDoS-checked before reaching here (maskflow_core.config.redos), not
    # re-validated.
    for pii_type, regex, base_confidence in extra_patterns:
        if pii_type in disabled_types:
            continue
        candidates.extend(_scan_pattern(text, pii_type, regex, base_confidence, None))

    return candidates


def _is_excluded(
    span: Span,
    exclusion_values: frozenset[str],
    exclusion_patterns: Sequence[re.Pattern[str]],
) -> bool:
    if span.text in exclusion_values:
        return True
    if not exclusion_patterns or len(span.text) > _MAX_EXCLUSION_MATCH_LEN:
        return False
    return any(pattern.search(span.text) for pattern in exclusion_patterns)


def _excise(text: str, spans: list[Span]) -> str:
    """Blank out `spans`' character ranges with a same-length filler, so the
    NER pass never re-detects (or gets confused by) PII already claimed by
    tier-0, while every char offset it produces still lines up with `text`.
    """
    if not spans:
        return text
    chars = list(text)
    for span in spans:
        for i in range(span.start, span.end):
            chars[i] = _EXCISION_CHAR
    return "".join(chars)


@overload
def detect(
    text: str,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    *,
    per_entity_threshold: Mapping[PIIType, float] | None = None,
    disabled_types: frozenset[PIIType] = frozenset(),
    extra_patterns: Sequence[tuple[PIIType, re.Pattern[str], float]] = (),
    exclusion_values: frozenset[str] = frozenset(),
    exclusion_patterns: Sequence[re.Pattern[str]] = (),
    return_rejected: Literal[False] = False,
) -> list[Span]: ...


@overload
def detect(
    text: str,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    *,
    per_entity_threshold: Mapping[PIIType, float] | None = None,
    disabled_types: frozenset[PIIType] = frozenset(),
    extra_patterns: Sequence[tuple[PIIType, re.Pattern[str], float]] = (),
    exclusion_values: frozenset[str] = frozenset(),
    exclusion_patterns: Sequence[re.Pattern[str]] = (),
    return_rejected: Literal[True],
) -> tuple[list[Span], list[Span]]: ...


def detect(
    text: str,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    *,
    per_entity_threshold: Mapping[PIIType, float] | None = None,
    disabled_types: frozenset[PIIType] = frozenset(),
    extra_patterns: Sequence[tuple[PIIType, re.Pattern[str], float]] = (),
    exclusion_values: frozenset[str] = frozenset(),
    exclusion_patterns: Sequence[re.Pattern[str]] = (),
    return_rejected: bool = False,
) -> list[Span] | tuple[list[Span], list[Span]]:
    """Detect PII in `text`, returning non-overlapping Spans sorted by
    position.

    The five keyword-only config params are how .maskflowrc-driven config
    reaches detection (see maskflow_core.config.engine.compile_config()) --
    every one of them defaults to "no effect", so a plain `detect(text)` or
    `detect(text, min_confidence)` call is unmodified both in output and in
    the code path it runs.

    `return_rejected` is opt-in and changes the return shape to
    `(accepted, rejected)`: `rejected` is every candidate span dropped for
    scoring below its entity type's threshold in the one authoritative
    resolve pass below (not spans that lost to an overlapping competitor).
    It does NOT include candidates a recognizer discarded before ever
    becoming a Span (a failed checksum, a NER label below its own
    per-recognizer threshold) -- those never had a Span to report. Default
    False, so mask()/mask_with_policy() and every existing `detect()` call
    site are unaffected in output, return type, and cost.
    """
    config = ResolveConfig(
        default_threshold=min_confidence,
        per_entity_threshold=dict(per_entity_threshold or {}),
    )

    pattern_candidates = _pattern_pass(text, disabled_types, extra_patterns)

    # Tier-0 excision: a provisional, regex-only resolve decides which regions
    # are already confidently claimed, so the NER pass runs on text with those
    # regions blanked out. This provisional pass exists only to build that
    # mask -- it is not the final answer, and its winners are not the only
    # candidates that get to compete below.
    tier0 = SpanSet(text, tuple(pattern_candidates)).resolve(config)
    excised_text = _excise(text, tier0)

    ner_candidates = detect_ner(excised_text, disabled_types=disabled_types)

    # The one authoritative resolution: every regex candidate (not just
    # tier0's winners) plus every NER candidate, resolved together exactly
    # once.
    all_candidates = tuple(pattern_candidates + ner_candidates)

    if not return_rejected:
        resolved = SpanSet(text, all_candidates).resolve(config)
        if not exclusion_values and not exclusion_patterns:
            return resolved
        return [s for s in resolved if not _is_excluded(s, exclusion_values, exclusion_patterns)]

    resolved, rejected = SpanSet(text, all_candidates).resolve_verbose(config)
    if exclusion_values or exclusion_patterns:
        resolved = [
            s for s in resolved if not _is_excluded(s, exclusion_values, exclusion_patterns)
        ]
        rejected = [
            s for s in rejected if not _is_excluded(s, exclusion_values, exclusion_patterns)
        ]
    return resolved, rejected


__all__ = ["detect", "Span", "PIIType"]
