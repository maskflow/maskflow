"""MaskFlow MCP proxy.

Wrap any MCP server; PII in outbound ``tools/call`` arguments is masked
before it reaches the backend, and results are unmasked on the way back,
with session-consistent placeholders.

``MaskflowMiddleware`` needs ``fastmcp``; the plain masking helpers in
``maskflow_mcp._masking`` do not. The fastmcp-facing names are imported
lazily so importing this package does not require ``fastmcp``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._masking import mask_arguments, unmask_json, unmask_text

__all__ = [
    "MaskflowMiddleware",
    "build_proxy",
    "SessionRegistry",
    "resolve_backend",
    "mask_arguments",
    "unmask_text",
    "unmask_json",
]

if TYPE_CHECKING:
    from .config import resolve_backend
    from .middleware import MaskflowMiddleware
    from .proxy import build_proxy
    from .sessions import SessionRegistry

_LAZY = {
    "MaskflowMiddleware": ("middleware", "MaskflowMiddleware"),
    "build_proxy": ("proxy", "build_proxy"),
    "SessionRegistry": ("sessions", "SessionRegistry"),
    "resolve_backend": ("config", "resolve_backend"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(f".{target[0]}", __name__), target[1])
