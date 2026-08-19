"""Orchestrates the regex, tier-0 excision, and NER passes into one resolved,
non-overlapping Span list. See CLAUDE.md 'Design decisions' #1-2 and
spanset.py for the resolution algorithm itself.
"""

from .context import apply_context_boost
from .entities import PIIType, Span
from .ner import detect_ner
from .registry import PATTERNS
from .spanset import ResolveConfig, SpanSet

DEFAULT_MIN_CONFIDENCE = 0.5

# A single fixed filler character, repeated to preserve length/char offsets,
# used to blank out tier-0 (already-resolved, high-confidence) regions before
# the NER pass runs. Non-word so spaCy's tokenizer never mistakes a run of it
# for a name/number; length-preserving so every downstream NER char offset
# still lines up with the original text.
_EXCISION_CHAR = "█"


def _pattern_pass(text: str) -> list[Span]:
    candidates: list[Span] = []

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
                    Span(
                        start=start,
                        end=end,
                        entity_type=pii_type,
                        score=round(confidence, 2),
                        recognizer=f"pattern:{pii_type}",
                        text=value,
                        validated=validated,
                    )
                )

    return candidates


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


def detect(text: str, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> list[Span]:
    """Detect PII in `text`, returning non-overlapping Spans sorted by position."""
    config = ResolveConfig(default_threshold=min_confidence)

    pattern_candidates = _pattern_pass(text)

    # Tier-0 excision: a provisional, regex-only resolve decides which regions
    # are already confidently claimed, so the NER pass runs on text with those
    # regions blanked out. This provisional pass exists only to build that
    # mask -- it is not the final answer, and its winners are not the only
    # candidates that get to compete below.
    tier0 = SpanSet(text, tuple(pattern_candidates)).resolve(config)
    excised_text = _excise(text, tier0)

    ner_candidates = detect_ner(excised_text)

    # The one authoritative resolution: every regex candidate (not just
    # tier0's winners) plus every NER candidate, resolved together exactly
    # once.
    return SpanSet(text, tuple(pattern_candidates + ner_candidates)).resolve(config)


__all__ = ["detect", "Span", "PIIType"]
