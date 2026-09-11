"""Recovers character offsets for adapters that only return matched
substrings, not (start, end) positions -- mask-privacy's Tier-2 NLP
entities and the LLM adapter both need this (see their modules' docstrings
for why offsets aren't available directly from those APIs).
"""

from __future__ import annotations


def locate_span(text: str, value: str, used_starts: set[int]) -> tuple[int, int] | None:
    """Finds the first occurrence of `value` in `text` whose start index
    isn't already in `used_starts`, claims it, and returns (start, end).
    Returns None if `value` doesn't occur (or every occurrence is already
    claimed) -- the caller drops that finding and counts it as unlocatable
    rather than guessing.
    """
    if not value:
        return None
    cursor = 0
    while True:
        idx = text.find(value, cursor)
        if idx == -1:
            return None
        if idx not in used_starts:
            used_starts.add(idx)
            return idx, idx + len(value)
        cursor = idx + 1
