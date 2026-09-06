"""Masking helpers for MCP tool-call arguments and results.

No ``fastmcp`` import here -- these operate on plain ``dict`` / ``list`` /
``str`` and a ``maskflow.Session``. The round-trip guarantees are the
session's; this module only decides which strings to hand it.
"""

from __future__ import annotations

import json
from typing import Any

from maskflow import Session

_MAX_DEPTH = 32
_MAX_ITEMS = 10_000


def mask_arguments(session: Session, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Mask string and numeric *values* in a ``tools/call`` arguments dict.
    Keys are never touched. Uses ``Session.mask_json`` so nested structures
    stay valid and identity is stable across calls in the session."""
    if not arguments:
        return arguments or {}
    masked = session.mask_json(arguments, max_depth=_MAX_DEPTH, max_items=_MAX_ITEMS)
    return masked if isinstance(masked, dict) else arguments


def unmask_text(session: Session, text: str) -> str:
    return session.unmask(text)


def unmask_json(session: Session, value: Any) -> Any:
    """Restore originals in every string leaf of a JSON-shaped structure."""
    if isinstance(value, str):
        return session.unmask(value)
    if isinstance(value, dict):
        return {k: unmask_json(session, v) for k, v in value.items()}
    if isinstance(value, list):
        return [unmask_json(session, v) for v in value]
    return value


def mask_new_json(session: Session, value: Any) -> Any:
    """Mask PII the tool *introduced* (a result that was not an echo of a
    masked argument), through the session so a value keeps its placeholder.
    Only used when ``mask_tool_results`` is on."""
    if isinstance(value, str):
        return session.mask(value)
    if isinstance(value, dict):
        return {k: mask_new_json(session, v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_new_json(session, v) for v in value]
    return value


def parse_json_string(raw: str) -> tuple[bool, Any]:
    try:
        return True, json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return False, raw
