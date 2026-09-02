"""Request-side masking helpers, shared by both provider adapters.

Every function takes an open ``maskflow.Session`` (so token identity is
stable across turns and tool calls) and a ``detections`` counter it
updates in place by inspecting the session mapping before/after -- that's
where the ``maskflow_detections_total`` metric comes from.

Response-side restoration is a structural walk (``unmask_json``): a literal
substring replace on serialized JSON would corrupt it the moment an
original value contains a quote or backslash, so string leaves are
unmasked one at a time.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

from maskflow import Session
from maskflow_core import Mapping

from .streaming import unmask_whole


def _count_new(
    session: Session, before: frozenset[str], detections: MutableMapping[str, int]
) -> None:
    mapping = session.mapping
    for token in mapping:
        if token not in before:
            entity_type = mapping[token].entity_type.value
            detections[entity_type] = detections.get(entity_type, 0) + 1


def mask_text(session: Session, text: str, detections: MutableMapping[str, int]) -> str:
    if not text:
        return text
    before = frozenset(session.mapping)
    masked = session.mask(text)
    _count_new(session, before, detections)
    return masked


def mask_json_value(
    session: Session,
    value: Any,
    detections: MutableMapping[str, int],
    *,
    max_depth: int,
    max_items: int,
) -> Any:
    before = frozenset(session.mapping)
    masked = session.mask_json(value, max_depth=max_depth, max_items=max_items)
    _count_new(session, before, detections)
    return masked


def mask_arguments_json(
    session: Session,
    raw: str,
    detections: MutableMapping[str, int],
    *,
    max_depth: int,
    max_items: int,
) -> str:
    """Mask a tool-call ``arguments`` string. It is meant to be a JSON
    object; if it does not parse, fall back to treating the whole string as
    text (still better than leaking PII in a malformed arg blob). Keys are
    never masked -- ``mask_json`` only touches string/number *values*."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return mask_text(session, raw, detections)
    masked = mask_json_value(session, parsed, detections, max_depth=max_depth, max_items=max_items)
    return json.dumps(masked, ensure_ascii=False)


def unmask_json(value: Any, mapping: Mapping) -> Any:
    """Recursively restore originals in every string leaf. Dict keys are
    left untouched (they are never masked on the way in)."""
    if isinstance(value, str):
        return unmask_whole(value, mapping)
    if isinstance(value, dict):
        return {key: unmask_json(child, mapping) for key, child in value.items()}
    if isinstance(value, list):
        return [unmask_json(child, mapping) for child in value]
    return value
