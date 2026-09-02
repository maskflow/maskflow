"""Operational endpoints: /healthz /readyz /metrics /v1/entities."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from maskflow_core import PIIType

from ..errors import SessionUnavailable
from ..observability import metrics

router = APIRouter()


@router.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness: the process is up. Never touches Redis or the upstream."""
    return JSONResponse({"status": "ok"})


@router.get("/readyz")
async def readyz(request: Request) -> Response:
    """Readiness: the session store is reachable and safe to use. Fails
    **closed** (503) if Redis eviction is not disabled -- an evicted
    session mid-conversation means unmask() finds nothing and a user sees
    raw ``<PERSON_NAME_1>`` placeholders."""
    store = request.app.state.snapshot_store
    try:
        await store.check_ready()
    except SessionUnavailable as exc:
        return JSONResponse(
            {"status": "not_ready", "reason": exc.message},
            status_code=503,
        )
    return JSONResponse({"status": "ready"})


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    payload, content_type = metrics.render()
    return Response(content=payload, media_type=content_type)


@router.get("/v1/entities")
async def entities() -> JSONResponse:
    """Every PII type the gateway's loaded recognizer packs can detect."""
    names = sorted(t.value for t in PIIType.values())
    return JSONResponse({"entities": names, "count": len(names)})


@router.get("/", include_in_schema=False)
async def root() -> PlainTextResponse:
    return PlainTextResponse(
        "MaskFlow Gateway. POST /v1/chat/completions, /v1/messages, "
        "/v1/embeddings, /v1/mask, /v1/unmask. See /docs."
    )
