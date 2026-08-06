"""Pure, stateless mask/unmask. No files, no DB -- the caller owns persistence of the mapping."""
from typing import NamedTuple

from .detection import DEFAULT_MIN_CONFIDENCE, detect


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

    for finding in findings:  # detect() returns non-overlapping findings sorted by start
        counters[finding.type.value] = counters.get(finding.type.value, 0) + 1
        token = f"<{finding.type.value}_{counters[finding.type.value]}>"
        mapping[token] = finding.value
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
