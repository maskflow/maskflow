"""Keyword-proximity confidence boosting.

Structural matches (email, credit card w/ Luhn, AWS keys, ...) are already
high-confidence on their own. Ambiguous matches (a bare 9-digit number, a
street-shaped line of text) need a nearby keyword to be trusted.

Core ships no keywords of its own -- CONTEXT_KEYWORDS starts empty and is
populated by whichever pack registers a type, via registry.register_pattern()
/ registry.register_ner_recognizer()'s `context_keywords` argument.
"""

from .entities import PIIType

WINDOW = 40

CONTEXT_KEYWORDS: dict[PIIType, tuple[str, ...]] = {}

BOOST = 0.4
MAX_CONFIDENCE = 0.99


def apply_context_boost(
    text: str, start: int, end: int, pii_type: PIIType, base_confidence: float
) -> float:
    keywords = CONTEXT_KEYWORDS.get(pii_type)
    if not keywords:
        return base_confidence

    window_start = max(0, start - WINDOW)
    window_end = min(len(text), end + WINDOW)
    nearby = text[window_start:start].lower() + " " + text[end:window_end].lower()

    if any(keyword in nearby for keyword in keywords):
        return min(MAX_CONFIDENCE, base_confidence + BOOST)
    return base_confidence
