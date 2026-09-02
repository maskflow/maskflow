"""Direct masking endpoints -- no upstream call.

``POST /v1/mask``   {"text": "..."}  ->  {"masked_text": "...", "mapping": {...}}
``POST /v1/unmask`` {"text": "...", "mapping": {...}}  ->  {"text": "..."}

With an ``X-Maskflow-Session`` header the mapping is kept server-side
instead of returned/accepted in the body -- the same session the chat
routes use, so tokens stay consistent across a whole agent run.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..masking import mask_text, unmask_whole
from ..observability import metrics

router = APIRouter()


@router.post("/v1/mask")
async def mask_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        return _bad('Body must be {"text": string}.')
    text = body["text"]
    manager = request.app.state.session_manager
    session_id = request.headers.get("x-maskflow-session")
    ttl = _parse_int(request.headers.get("x-maskflow-session-ttl"))
    detections: dict[str, int] = {}

    async with manager.use(session_id, ttl_seconds=ttl) as managed:
        masked = mask_text(managed.session, text, detections)
        metrics.record_detections(detections, direction="request")
        if managed.keyed:
            await managed.persist()
            return JSONResponse({"masked_text": masked, "session": session_id})
        mapping = {
            token: managed.session.mapping[token].original for token in managed.session.mapping
        }
        return JSONResponse({"masked_text": masked, "mapping": mapping})


@router.post("/v1/unmask")
async def unmask_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        return _bad('Body must be {"text": string, "mapping": {token: original}}.')
    text = body["text"]
    session_id = request.headers.get("x-maskflow-session")

    if session_id is not None:
        manager = request.app.state.session_manager
        async with manager.use(session_id) as managed:
            return JSONResponse({"text": unmask_whole(text, managed.session.mapping)})

    mapping = body.get("mapping")
    if not isinstance(mapping, dict):
        return _bad("Without an X-Maskflow-Session header, 'mapping' is required.")
    result = text
    for token, original in mapping.items():
        if isinstance(token, str) and isinstance(original, str):
            result = result.replace(token, original)
    return JSONResponse({"text": result})


def _bad(message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": "invalid_request"}}, status_code=400)


def _parse_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
