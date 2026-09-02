"""/v1/embeddings -- the RAG path. Inputs are masked *before* they reach
the embedding model, so PII never enters a vector index. The response is
just vectors; there is nothing to unmask (the mapping is still persisted on
a keyed session so a later retrieval-augmented completion stays
consistent).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..providers import openai
from ._proxy import run_proxy

router = APIRouter()


@router.post("/v1/embeddings")
async def embeddings(request: Request) -> Response:
    return await run_proxy(
        request,
        route="embeddings",
        provider="openai",
        upstream_path="/embeddings",
        mask_request=lambda managed, body, det: openai.mask_embeddings_request(
            managed.session, body, det
        ),
        unmask_response=lambda body, mapping: body,
        stream_response=None,
    )
