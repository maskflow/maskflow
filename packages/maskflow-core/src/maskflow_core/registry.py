"""Extension point for packs to add PII types and recognizers without editing
maskflow-core.

A pack (e.g. maskflow-pack-intl, maskflow-pack-india) calls register_pattern()
for a regex-based recognizer or register_ner_recognizer() for a spaCy-label-based
one; both register the PIIType itself first if it isn't already known, and both
accept optional context_keywords that feed context.apply_context_boost(). Core
owns none of the state these populate -- PATTERNS and NER_RECOGNIZERS start
empty, and detection.py/ner.py read from whatever's been registered so far.

This is a manual registration function, not the entry-point-based plugin
auto-discovery ("maskflow.recognizers") described for the target architecture
-- that needs real installable pack packages to build and test against and is
separate follow-up work. This gives packs something to call today.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .context import CONTEXT_KEYWORDS
from .entities import PIIType

# A plain type-alias assignment, not an annotation -- `from __future__ import
# annotations` defers annotation evaluation but not this, so `float | None`
# here (unlike everywhere else in this file) would still break on Python 3.9.
Validator = Callable[[str], Optional[float]]

# type -> [(regex, base_confidence, validator), ...], appended to by register_pattern()
PATTERNS: dict[PIIType, list[tuple[re.Pattern[str], float, Validator | None]]] = {}


@dataclass(frozen=True)
class NerMapping:
    """How one spaCy entity label maps onto a PIIType."""

    pii_type: PIIType
    base_confidence: float
    # A finding is dropped unless its confidence (after context boost) meets
    # this bar -- mirrors detect()'s min_confidence filter, but applied per
    # label since NER base confidences vary far more than regex matches do.
    threshold: float = 0.0


# spaCy label (e.g. "PERSON") -> NerMapping, appended to by register_ner_recognizer()
NER_RECOGNIZERS: dict[str, NerMapping] = {}


def register_pattern(
    pii_type: str,
    regex: re.Pattern[str],
    base_confidence: float,
    validator: Validator | None = None,
    context_keywords: tuple[str, ...] | None = None,
) -> PIIType:
    """Register a new (regex, base_confidence, validator) rule for `pii_type`,
    registering the PIIType itself first if it isn't already known."""
    registered_type = PIIType.register(pii_type)
    PATTERNS.setdefault(registered_type, []).append((regex, base_confidence, validator))
    if context_keywords:
        CONTEXT_KEYWORDS[registered_type] = context_keywords
    return registered_type


def register_ner_recognizer(
    spacy_label: str,
    pii_type: str,
    base_confidence: float,
    threshold: float = 0.0,
    context_keywords: tuple[str, ...] | None = None,
) -> PIIType:
    """Map a spaCy entity label (e.g. "PERSON") onto `pii_type`, registering the
    PIIType itself first if it isn't already known. ner.py's generic NER pass
    reads NER_RECOGNIZERS to turn matching doc.ents into Findings."""
    registered_type = PIIType.register(pii_type)
    NER_RECOGNIZERS[spacy_label] = NerMapping(registered_type, base_confidence, threshold)
    if context_keywords:
        CONTEXT_KEYWORDS[registered_type] = context_keywords
    return registered_type
