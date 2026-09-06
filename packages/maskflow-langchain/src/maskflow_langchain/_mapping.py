"""Conversions between a ``maskflow.Session`` mapping and LangChain's
``MappingDataType`` (``{entity_type: {anonymized: original}}``).

The nested-by-entity-type shape is what ``PresidioReversibleAnonymizer``
exposes as ``.deanonymizer_mapping`` / ``.anonymizer_mapping`` and what its
``save``/``load`` round-trips, so a chain that inspects or persists the
mapping keeps working after the import swap.
"""

from __future__ import annotations

from maskflow import Session

from .matching import MappingDataType


def session_deanonymizer_mapping(session: Session) -> MappingDataType:
    """``{ENTITY: {<token>: original}}`` for every reversible entry in the
    session's current mapping."""
    out: MappingDataType = {}
    mapping = session.mapping
    for token in mapping:
        entry = mapping[token]
        if not entry.reversible:
            continue
        out.setdefault(entry.entity_type.value, {})[token] = entry.original
    return out


def invert(mapping_data: MappingDataType) -> MappingDataType:
    """``{ENTITY: {token: original}}`` -> ``{ENTITY: {original: token}}``."""
    return {
        entity_type: {original: anon for anon, original in inner.items()}
        for entity_type, inner in mapping_data.items()
    }


def flat_token_pairs(mapping_data: MappingDataType) -> dict[str, str]:
    """Flatten to ``{<token>: original}`` for whole-text or streaming unmask."""
    pairs: dict[str, str] = {}
    for inner in mapping_data.values():
        pairs.update(inner)
    return pairs


def merge_into(dst: MappingDataType, src: MappingDataType) -> None:
    """Merge ``src`` into ``dst`` in place; existing token->original entries
    are not overwritten."""
    for entity_type, inner in src.items():
        target = dst.setdefault(entity_type, {})
        for anon, original in inner.items():
            target.setdefault(anon, original)
