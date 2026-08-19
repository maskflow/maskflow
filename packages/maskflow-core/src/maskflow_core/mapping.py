"""Reversible-mapping model: MappingEntry records what mask_with_policy()
substituted a Span with; Mapping is the token -> MappingEntry container it
returns, and the same object unmask() reads back (see masking.py's unmask(),
which also still accepts the legacy dict[str, str] mapping from mask()
unchanged).
"""

from __future__ import annotations

from collections.abc import ItemsView, Iterator, KeysView, ValuesView
from dataclasses import dataclass, field
from typing import Any

from .entities import PIIType
from .strategies import Strategy


@dataclass(frozen=True)
class MappingEntry:
    """One substitution mask_with_policy() made. `original` is repr-excluded
    -- same discipline as Span.text (CLAUDE.md rule 1: raw PII must never
    surface via default dataclass repr)."""

    token: str
    entity_type: PIIType
    strategy: Strategy
    reversible: bool
    original: str = field(repr=False)


class Mapping:
    """dict-like token -> MappingEntry container. Implements the surface
    unmask() and callers need from the legacy dict[str, str] mapping
    (`__getitem__`, `__contains__`, `__iter__`, `__len__`, `.items()`,
    `.get()`, `.values()`), plus JSON (de)serialization for MappingStore."""

    def __init__(self, entries: dict[str, MappingEntry] | None = None) -> None:
        self._entries: dict[str, MappingEntry] = dict(entries or {})

    def __getitem__(self, token: str) -> MappingEntry:
        return self._entries[token]

    def __setitem__(self, token: str, entry: MappingEntry) -> None:
        self._entries[token] = entry

    def __contains__(self, token: object) -> bool:
        return token in self._entries

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return self._entries == other._entries
        return NotImplemented

    def __repr__(self) -> str:
        # Entries themselves are repr-safe (MappingEntry.original is
        # repr-excluded), so the default-ish repr here is fine -- listing
        # tokens is the point of a repr, not a leak.
        return f"Mapping({list(self._entries)!r})"

    def items(self) -> ItemsView[str, MappingEntry]:
        return self._entries.items()

    def keys(self) -> KeysView[str]:
        return self._entries.keys()

    def values(self) -> ValuesView[MappingEntry]:
        return self._entries.values()

    def get(self, token: str, default: MappingEntry | None = None) -> MappingEntry | None:
        return self._entries.get(token, default)

    def to_json(self) -> dict[str, Any]:
        """Serialize for MappingStore persistence. Includes `original` --
        a caller persisting this is choosing to persist plaintext (encrypted
        at rest by EncryptedFileMappingStore); it is never logged or printed
        by this method."""
        return {
            token: {
                "entity_type": entry.entity_type.value,
                "strategy": entry.strategy.value,
                "reversible": entry.reversible,
                "original": entry.original,
            }
            for token, entry in self._entries.items()
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Mapping:
        entries = {
            token: MappingEntry(
                token=token,
                entity_type=PIIType.register(fields["entity_type"]),
                strategy=Strategy(fields["strategy"]),
                reversible=fields["reversible"],
                original=fields["original"],
            )
            for token, fields in data.items()
        }
        return cls(entries)
