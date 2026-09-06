"""``MaskflowMiddleware`` -- masks PII in outbound ``tools/call`` arguments
and restores it in the results, for a FastMCP proxy.

    from fastmcp import FastMCP
    from maskflow_mcp import MaskflowMiddleware

    proxy = FastMCP.as_proxy("npx -y @modelcontextprotocol/server-github")
    proxy.add_middleware(MaskflowMiddleware())
    proxy.run()

On ``on_call_tool``: the arguments dict is walked (string / numeric values
only, keys never) and masked through the connection's session, so the
backend tool never sees the real values. The result's text content is then
unmasked, restoring any placeholders the tool echoed. With
``mask_tool_results=True`` (off by default) raw PII the tool *introduced*
is also masked, through the same session, so the agent does not see it
either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from ._masking import mask_arguments
from .sessions import SessionRegistry

if TYPE_CHECKING:
    from maskflow import Session

_DEFAULT_KEY = "stdio"


class MaskflowMiddleware(Middleware):
    def __init__(
        self,
        *,
        min_confidence: float | None = None,
        patterns_only: bool = False,
        mask_tool_results: bool = False,
        session_ttl_seconds: float = 3600,
        registry: SessionRegistry | None = None,
    ) -> None:
        self.mask_tool_results = mask_tool_results
        self._registry = registry or SessionRegistry(
            min_confidence=min_confidence,
            patterns_only=patterns_only,
            ttl_seconds=session_ttl_seconds,
        )

    # -- session key -----------------------------------------------------
    def _session(self, context: MiddlewareContext[Any]) -> Session:
        fc = getattr(context, "fastmcp_context", None)
        key = getattr(fc, "session_id", None) or _DEFAULT_KEY
        return self._registry.get(str(key))

    # -- hook ----------------------------------------------------------------
    async def on_call_tool(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        session = self._session(context)

        message = context.message
        message.arguments = mask_arguments(session, getattr(message, "arguments", None))

        result = await call_next(context)
        self._transform_result(session, result)
        return result

    # -- result rewriting -------------------------------------------------
    def _transform_result(self, session: Session, result: Any) -> None:
        for block in getattr(result, "content", None) or []:
            self._transform_block(session, block)

        structured = getattr(result, "structured_content", None)
        if structured is not None:
            result.structured_content = self._transform_value(session, structured)

    def _transform_block(self, session: Session, block: Any) -> None:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            block.text = self._transform_text(session, text)
            return
        # EmbeddedResource -> .resource (TextResourceContents has .text)
        resource = getattr(block, "resource", None)
        if resource is None:
            return
        inner = getattr(resource, "text", None)
        if isinstance(inner, str):
            resource.text = self._transform_text(session, inner)

    def _transform_text(self, session: Session, text: str) -> str:
        out = session.unmask(text)
        if self.mask_tool_results:
            out = session.mask(out)
        return out

    def _transform_value(self, session: Session, value: Any) -> Any:
        if isinstance(value, str):
            return self._transform_text(session, value)
        if isinstance(value, dict):
            return {k: self._transform_value(session, v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._transform_value(session, v) for v in value]
        return value

    def close(self) -> None:
        self._registry.close()
