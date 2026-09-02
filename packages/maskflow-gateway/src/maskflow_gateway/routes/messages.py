from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..providers import anthropic
from ._proxy import run_proxy

router = APIRouter()


@router.post("/v1/messages")
async def messages(request: Request) -> Response:
    settings = request.app.state.settings
    md, mi = settings.tool_call_max_depth, settings.tool_call_max_items
    return await run_proxy(
        request,
        route="messages",
        provider="anthropic",
        upstream_path="/messages",
        mask_request=lambda managed, body, det: anthropic.mask_messages_request(
            managed.session, body, det, max_depth=md, max_items=mi
        ),
        unmask_response=lambda body, mapping: anthropic.unmask_messages_response(body, mapping),
        stream_response=lambda mapping, src: anthropic.stream_messages_response(mapping, src),
    )
