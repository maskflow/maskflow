"""apply_context_boost's keyword-proximity mechanism, proven with a synthetic
registered type. Previously only exercised indirectly through built-in types
in the (now-relocated) accuracy suite; core needs standalone coverage of its
own engine behavior.
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
