"""Orchestrates the regex, context, and NER passes into one deduplicated finding list."""

from .context import apply_context_boost
from .entities import Finding, PIIType
from .ner import detect_ner
from .registry import PATTERNS

DEFAULT_MIN_CONFIDENCE = 0.5


def _regex_pass(text: str) -> list[Finding]:
    candidates: list[Finding] = []

    for pii_type, rules in PATTERNS.items():
        for regex, base_confidence, validator in rules:
            for match in regex.finditer(text):
                if match.re.groups:
                    start, end = match.span(1)
                    value = match.group(1)
                else:
                    start, end = match.span(0)
                    value = match.group(0)

                confidence = base_confidence
                validated = False
                if validator is not None:
                    adjusted = validator(value)
                    if adjusted is None:
                        continue
                    confidence = adjusted
                    validated = True

                confidence = apply_context_boost(text, start, end, pii_type, confidence)
                candidates.append(
                    Finding(pii_type, value, start, end, round(confidence, 2), validated)
                )

    return candidates


def _spans_overlap(a: Finding, b: Finding) -> bool:
    return a.start < b.end and b.start < a.end


def _merge_overlaps(candidates: list[Finding]) -> list[Finding]:
    accepted: list[Finding] = []
    # validated desc, confidence desc, length desc, start asc -- a
    # checksum-validated span always beats an overlapping unvalidated one,
    # regardless of raw confidence.
    ordered = sorted(
        candidates,
        key=lambda f: (not f.validated, -f.confidence, -len(f.value), f.start),
    )
    for finding in ordered:
        if not any(_spans_overlap(finding, kept) for kept in accepted):
            accepted.append(finding)
    return sorted(accepted, key=lambda f: f.start)


def detect(text: str, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> list[Finding]:
    """Detect PII in `text`, returning non-overlapping Findings sorted by position."""
    candidates = _regex_pass(text) + detect_ner(text)
    above_threshold = [f for f in candidates if f.confidence >= min_confidence]
    return _merge_overlaps(above_threshold)


__all__ = ["detect", "Finding", "PIIType"]
