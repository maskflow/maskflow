"""A tiny dotted-path extractor for pulling text out of decoded JSON rows.

Grammar (no regex, no backtracking -- CLAUDE.md rule 3):

    selector := segment ("." segment)*
    segment  := KEY | KEY "[]"        # "[]" means "iterate every list item"

    messages[].content   -> every message's .content
    choices[].message.content
    input                -> a single top-level string
    data.prompt

A selector yields zero or more strings. Non-string leaves (numbers, null,
nested objects, a missing key) are skipped, not errored -- a scan over a
heterogeneous dump should extract what it can and move on.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from .errors import SourceConfigError

_MAX_SEGMENTS = 32  # a selector this deep is a mistake, not a real schema


@dataclass(frozen=True)
class _Segment:
    key: str
    iterate: bool


@dataclass(frozen=True)
class FieldSelector:
    raw: str
    _segments: tuple[_Segment, ...]

    @classmethod
    def parse(cls, raw: str) -> FieldSelector:
        raw = raw.strip()
        if not raw:
            raise SourceConfigError("--field cannot be empty (e.g. --field messages[].content)")
        parts = raw.split(".")
        if len(parts) > _MAX_SEGMENTS:
            raise SourceConfigError(f"--field {raw!r} has too many segments (max {_MAX_SEGMENTS})")
        segments: list[_Segment] = []
        for part in parts:
            iterate = part.endswith("[]")
            key = part[:-2] if iterate else part
            if not key or not all(c.isalnum() or c in "_-" for c in key):
                raise SourceConfigError(
                    f"--field {raw!r}: segment {part!r} is not a plain key "
                    "(letters, digits, _ , - ; optional trailing [])"
                )
            segments.append(_Segment(key, iterate))
        return cls(raw=raw, _segments=tuple(segments))

    def extract(self, row: object) -> Iterator[str]:
        yield from _walk(row, self._segments)


def _walk(node: object, segments: tuple[_Segment, ...]) -> Iterator[str]:
    if not segments:
        if isinstance(node, str):
            yield node
        return
    head, rest = segments[0], segments[1:]
    if not isinstance(node, dict):
        return
    value = node.get(head.key)
    if head.iterate:
        if isinstance(value, list):
            for item in value:
                yield from _walk(item, rest)
    else:
        yield from _walk(value, rest)


def extract_all(row: object, selectors: tuple[FieldSelector, ...]) -> list[str]:
    """Every string every selector matches, in selector then document order."""
    out: list[str] = []
    for sel in selectors:
        out.extend(sel.extract(row))
    return out


def first_str(row: object, selector: str | None) -> str | None:
    """Single-value convenience for metadata fields (--provider-field etc.):
    the first string `selector` matches, or None."""
    if selector is None:
        return None
    for value in FieldSelector.parse(selector).extract(row):
        return value
    return None
