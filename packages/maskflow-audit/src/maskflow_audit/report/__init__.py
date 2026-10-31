"""Rendering. `render(summary, fmt)` and nothing else reaches the outside.

Same split as maskflow-cli's scan report: one PII-free data model
(summary.py) that every renderer reads from, so the leak question is
answerable by inspecting the model rather than by auditing each format.
"""

from __future__ import annotations

from collections.abc import Callable

from .html import TRUST_LINE, render_html
from .json_out import render_json
from .summary import AUDIT_SCHEMA_VERSION, AuditSummary

RENDERERS: dict[str, Callable[[AuditSummary], str]] = {
    "json": render_json,
    "html": render_html,
}

#: Every format the audit can write.
FORMATS: tuple[str, ...] = tuple(RENDERERS)


def render(summary: AuditSummary, fmt: str) -> str:
    try:
        return RENDERERS[fmt](summary)
    except KeyError:
        raise ValueError(f"unknown format {fmt!r}; choose one of: {', '.join(FORMATS)}") from None


__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "FORMATS",
    "RENDERERS",
    "TRUST_LINE",
    "AuditSummary",
    "render",
    "render_html",
    "render_json",
]
