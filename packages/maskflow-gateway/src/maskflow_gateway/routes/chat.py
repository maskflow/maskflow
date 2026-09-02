from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..providers import openai
from ._proxy import run_proxy

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    settings = request.app.state.settings
    md, mi = settings.tool_call_max_depth, settings.tool_call_max_items
    return await run_proxy(
        request,
        route="chat_completions",
        provider="openai",
        upstream_path="/chat/completions",
        mask_request=lambda managed, body, det: openai.mask_chat_request(
            managed.session, body, det, max_depth=md, max_items=mi
        ),
        unmask_response=lambda body, mapping: openai.unmask_chat_response(body, mapping),
        stream_response=lambda mapping, src: openai.stream_chat_response(mapping, src),
    )
