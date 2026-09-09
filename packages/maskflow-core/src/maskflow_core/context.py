"""Keyword-proximity confidence adjustment.

Structural matches (email, credit card w/ Luhn, AWS keys, ...) are already
high-confidence on their own. Ambiguous matches (a bare 9-digit number, a
street-shaped line of text) need a nearby keyword to be trusted -- and a
nearby *negative* keyword ("this is just an example Aadhaar number: ...")
should push them the other way.

Two mechanisms, applied in this order per CLAUDE.md's confidence formula
(`+ context_boost - negative_context`):

* apply_context_boost() -- a nearby positive keyword raises confidence.
* apply_negative_context() -- a nearby negative keyword lowers it (floored
  at 0.0 so Span's [0, 1] invariant holds). Applied regardless of whether a
  checksum validator passed: the formula subtracts negative_context after
  the validator multiplier, and a checksum-valid *synthetic* identifier next
  to the word "example" is exactly the case this exists to suppress.

Core ships no keywords of its own -- both CONTEXT_KEYWORDS and
NEGATIVE_CONTEXT_KEYWORDS start empty and are populated by whichever pack
registers a type, via registry.register_pattern() /
register_custom_recognizer() / register_ner_recognizer()'s
`context_keywords` / `negative_context_keywords` arguments.
"""

from .entities import ExplanationStep, PIIType

WINDOW = 40

CONTEXT_KEYWORDS: dict[PIIType, tuple[str, ...]] = {}
NEGATIVE_CONTEXT_KEYWORDS: dict[PIIType, tuple[str, ...]] = {}

BOOST = 0.4
PENALTY = 0.3
MAX_CONFIDENCE = 0.99


def _nearby(text: str, start: int, end: int) -> str:
    """The lowercased text within WINDOW chars on either side of [start, end),
    joined by a space so a keyword can't straddle the gap. Shared by both the
    positive and negative proximity checks."""
    window_start = max(0, start - WINDOW)
    window_end = min(len(text), end + WINDOW)
    return text[window_start:start].lower() + " " + text[end:window_end].lower()


def apply_context_boost(
    text: str, start: int, end: int, pii_type: PIIType, base_confidence: float
) -> tuple[float, ExplanationStep]:
    keywords = CONTEXT_KEYWORDS.get(pii_type)
    if not keywords:
        return base_confidence, ExplanationStep(rule="context", outcome="not_configured")

    nearby = _nearby(text, start, end)

    for keyword in keywords:
        if keyword in nearby:
            boosted = min(MAX_CONFIDENCE, base_confidence + BOOST)
            step = ExplanationStep(
                rule="context",
                outcome="boosted",
                delta=round(boosted - base_confidence, 2),
                detail=f'keyword "{keyword}" found within {WINDOW} chars',
            )
            return boosted, step

    step = ExplanationStep(
        rule="context", outcome="no_match", detail=f"no context keyword found within {WINDOW} chars"
    )
    return base_confidence, step


def apply_negative_context(
    text: str, start: int, end: int, pii_type: PIIType, base_confidence: float
) -> tuple[float, ExplanationStep]:
    """Lower `base_confidence` by PENALTY (floored at 0.0) when a registered
    negative keyword for `pii_type` sits within WINDOW chars of the match --
    the suppression half of the confidence formula. Runs after
    apply_context_boost(), so "example aadhaar number 1234 ..." is boosted
    then suppressed, and both steps appear in the explanation trail."""
    keywords = NEGATIVE_CONTEXT_KEYWORDS.get(pii_type)
    if not keywords:
        return base_confidence, ExplanationStep(rule="negative_context", outcome="not_configured")

    nearby = _nearby(text, start, end)

    for keyword in keywords:
        if keyword in nearby:
            reduced = max(0.0, base_confidence - PENALTY)
            step = ExplanationStep(
                rule="negative_context",
                outcome="suppressed",
                delta=round(reduced - base_confidence, 2),
                detail=f'keyword "{keyword}" found within {WINDOW} chars',
            )
            return reduced, step

    step = ExplanationStep(
        rule="negative_context",
        outcome="no_match",
        detail=f"no negative context keyword found within {WINDOW} chars",
    )
    return base_confidence, step
