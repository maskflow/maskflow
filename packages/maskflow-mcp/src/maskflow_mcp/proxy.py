"""``build_proxy`` -- a FastMCP proxy for a backend MCP server with the
MaskFlow masking middleware attached."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .middleware import MaskflowMiddleware


def build_proxy(
    backend: str | dict[str, Any],
    *,
    name: str = "maskflow-mcp",
    min_confidence: float | None = None,
    patterns_only: bool = False,
    mask_tool_results: bool = False,
    session_ttl_seconds: float = 3600,
) -> FastMCP:
    """``backend`` is anything ``FastMCP.as_proxy`` accepts: a URL string, a
    ``.py`` / ``.js`` path, or a canonical MCP config dict
    (``{"mcpServers": {...}}``). See ``maskflow_mcp.config.resolve_backend``."""
    proxy: FastMCP = FastMCP.as_proxy(backend, name=name)
    proxy.add_middleware(
        MaskflowMiddleware(
            min_confidence=min_confidence,
            patterns_only=patterns_only,
            mask_tool_results=mask_tool_results,
            session_ttl_seconds=session_ttl_seconds,
        )
    )
    return proxy
