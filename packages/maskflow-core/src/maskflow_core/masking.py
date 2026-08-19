"""Pure, stateless mask/unmask. No files, no DB -- the caller owns persistence of the mapping."""

import re
import secrets
from typing import NamedTuple

from .detection import DEFAULT_MIN_CONFIDENCE, detect

# Matches both plain (<EMAIL_1>) and nonce-suffixed (<EMAIL_1_a4f9>) tokens, so
# input text that already contains placeholder-lookalike substrings is detected
# and never collided with.
_RESERVED_TOKEN_RE = re.compile(r"<[A-Z_]+_\d+(?:_[0-9a-f]+)?>")


class MaskResult(NamedTuple):
    masked_text: str
    mapping: dict[str, str]


def mask(text: str, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> MaskResult:
    """Replace detected PII with `<TYPE_n>` tokens, returning the masked text and a
    {token: original_value} mapping the caller can use to unmask a later response."""
    spans = detect(text, min_confidence=min_confidence)

    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}
    pieces: list[str] = []
    cursor = 0
    # Placeholder-lookalike text already present in the input (e.g. someone's
    # prompt literally contains "<EMAIL_1>") must never collide with a token
    # we assign -- track everything already claimed, real or lookalike.
    reserved: set[str] = set(_RESERVED_TOKEN_RE.findall(text))

    for span in spans:  # detect() returns non-overlapping spans sorted by start
        entity_type = span.entity_type.value
        counters[entity_type] = counters.get(entity_type, 0) + 1
        token = f"<{entity_type}_{counters[entity_type]}>"
        while token in reserved:
            token = f"<{entity_type}_{counters[entity_type]}_{secrets.token_hex(2)}>"
        mapping[token] = span.text
        reserved.add(token)
        pieces.append(text[cursor : span.start])
        pieces.append(token)
        cursor = span.end

    pieces.append(text[cursor:])
    return MaskResult("".join(pieces), mapping)


def unmask(masked_text: str, mapping: dict[str, str]) -> str:
    """Restore original values from a mapping produced by `mask()`."""
    result = masked_text
    for token, original in mapping.items():
        result = result.replace(token, original)
    return result
