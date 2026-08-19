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
    findings = detect(text, min_confidence=min_confidence)

    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}
    pieces: list[str] = []
    cursor = 0
    # Placeholder-lookalike text already present in the input (e.g. someone's
    # prompt literally contains "<EMAIL_1>") must never collide with a token
    # we assign -- track everything already claimed, real or lookalike.
    reserved: set[str] = set(_RESERVED_TOKEN_RE.findall(text))

    for finding in findings:  # detect() returns non-overlapping findings sorted by start
        counters[finding.type.value] = counters.get(finding.type.value, 0) + 1
        token = f"<{finding.type.value}_{counters[finding.type.value]}>"
        while token in reserved:
            token = f"<{finding.type.value}_{counters[finding.type.value]}_{secrets.token_hex(2)}>"
        mapping[token] = finding.value
        reserved.add(token)
        pieces.append(text[cursor:finding.start])
        pieces.append(token)
        cursor = finding.end

    pieces.append(text[cursor:])
    return MaskResult("".join(pieces), mapping)


def unmask(masked_text: str, mapping: dict[str, str]) -> str:
    """Restore original values from a mapping produced by `mask()`."""
    result = masked_text
    for token, original in mapping.items():
        result = result.replace(token, original)
    return result
