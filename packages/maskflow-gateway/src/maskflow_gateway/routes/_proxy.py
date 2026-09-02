"""The shared proxy flow for /v1/chat/completions, /v1/messages and
/v1/embeddings.

Order of operations (identical for streaming and non-streaming, so an
error still produces a real HTTP status before any SSE byte is committed):

1. size-limit + JSON parse the request body
2. per-key rate limit
3. open the session (restore from the store if the client sent
   ``X-Maskflow-Session``)
4. mask the request  ->  observe the ``mask`` stage latency + detections
5. persist the session snapshot  (before the upstream call: a crash
   mid-stream must not lose the mapping needed to unmask)
6. call the upstream, peeking its status before deciding stream vs error
7. restore the response  (structural for JSON, incremental for SSE)
8. record request/latency/detection metrics; close the session
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..errors import GatewayError, RateLimited, RequestTooLarge
from ..masking import unmask_whole
from ..observability import metrics
from ..sessions import ManagedSession
from ..streaming import format_sse
from ..upstream import filter_response_headers, forward_request_headers

logger = logging.getLogger("maskflow_gateway.proxy")

# (managed_session, body, detections) -> masked_body
MaskFn = Callable[[ManagedSession, dict[str, Any], dict[str, int]], dict[str, Any]]
# (response_json, mapping) -> restored_json
UnmaskFn = Callable[[dict[str, Any], Any], dict[str, Any]]
# (mapping, upstream_byte_iter) -> client_byte_iter
StreamFn = Callable[[Any, AsyncIterator[bytes]], AsyncIterator[bytes]]


async def run_proxy(
    request: Request,
    *,
    route: str,
    provider: str,
    upstream_path: str,
    mask_request: MaskFn,
    unmask_response: UnmaskFn,
    stream_response: StreamFn | None,
) -> Response:
    app = request.app
    settings = app.state.settings

    raw = await request.body()
    if len(raw) > settings.max_request_bytes:
        raise RequestTooLarge(settings.max_request_bytes)
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return _error_response(400, "invalid_request", "Request body must be a JSON object.")

    limiter = app.state.rate_limiter
    from ..ratelimit import client_key

    allowed, retry_after = await limiter.check(client_key(request.headers))
    if not allowed:
        raise RateLimited(retry_after)

    session_id = request.headers.get("x-maskflow-session")
    ttl_header = request.headers.get("x-maskflow-session-ttl")
    ttl_seconds = _parse_int(ttl_header)

    want_stream = bool(body.get("stream")) and stream_response is not None

    manager = app.state.session_manager
    cm = manager.use(session_id, ttl_seconds=ttl_seconds)
    managed = await cm.__aenter__()
    detections: dict[str, int] = {}
    try:
        t0 = time.perf_counter()
        masked_body = mask_request(managed, body, detections)
        metrics.STAGE_LATENCY.labels(stage="mask").observe(time.perf_counter() - t0)
        metrics.record_detections(detections, direction="request")

        await managed.persist()

        mapping = managed.session.mapping
        headers = forward_request_headers(request.headers, settings)
        url = f"{provider_base_url(app, provider)}{upstream_path}"

        upstream = app.state.upstream
        t_up = time.perf_counter()

        if want_stream:
            stream_cm = upstream.stream_json(url, headers, masked_body)
            resp = await stream_cm.__aenter__()
            if resp.status_code >= 400:
                err_bytes = await resp.aread()
                await stream_cm.__aexit__(None, None, None)
                await cm.__aexit__(None, None, None)
                metrics.REQUESTS.labels(
                    route=route, provider=provider, status=metrics.status_class(resp.status_code)
                ).inc()
                metrics.ERRORS.labels(provider=provider, type="upstream_error").inc()
                return Response(
                    content=err_bytes,
                    status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json"),
                )

            assert stream_response is not None
            client_headers = filter_response_headers(resp)

            async def body_iter() -> AsyncIterator[bytes]:
                try:
                    async for piece in stream_response(mapping, resp.aiter_bytes()):
                        yield piece
                except GatewayError as exc:
                    yield format_sse(json.dumps(exc.to_body())).encode("utf-8")
                except Exception:  # noqa: BLE001
                    logger.exception("stream transform failed", extra={"provider": provider})
                    yield format_sse(
                        json.dumps({"error": {"message": "stream transform failed"}})
                    ).encode("utf-8")
                finally:
                    metrics.STAGE_LATENCY.labels(stage="upstream").observe(
                        time.perf_counter() - t_up
                    )
                    await stream_cm.__aexit__(None, None, None)
                    await cm.__aexit__(None, None, None)
                    metrics.REQUESTS.labels(route=route, provider=provider, status="2xx").inc()

            logger.info(
                "proxied (stream)",
                extra={
                    "route": route,
                    "provider": provider,
                    "session": bool(session_id),
                    "detections": sum(detections.values()),
                },
            )
            return StreamingResponse(
                body_iter(), media_type="text/event-stream", headers=client_headers
            )

        # ---- non-streaming ------------------------------------------------
        upstream_resp = await upstream.post_json(url, headers, masked_body)
        metrics.STAGE_LATENCY.labels(stage="upstream").observe(time.perf_counter() - t_up)

        if upstream_resp.status_code >= 400:
            await cm.__aexit__(None, None, None)
            metrics.REQUESTS.labels(
                route=route,
                provider=provider,
                status=metrics.status_class(upstream_resp.status_code),
            ).inc()
            metrics.ERRORS.labels(provider=provider, type="upstream_error").inc()
            return Response(
                content=upstream_resp.content,
                status_code=upstream_resp.status_code,
                media_type=upstream_resp.headers.get("content-type", "application/json"),
            )

        upstream_json = upstream_resp.json()
        t_un = time.perf_counter()
        restored = unmask_response(upstream_json, mapping)
        metrics.STAGE_LATENCY.labels(stage="unmask").observe(time.perf_counter() - t_un)

        await cm.__aexit__(None, None, None)
        metrics.REQUESTS.labels(route=route, provider=provider, status="2xx").inc()
        logger.info(
            "proxied",
            extra={
                "route": route,
                "provider": provider,
                "session": bool(session_id),
                "detections": sum(detections.values()),
            },
        )
        return JSONResponse(restored, headers=filter_response_headers(upstream_resp))

    except GatewayError:
        await cm.__aexit__(None, None, None)
        metrics.ERRORS.labels(provider=provider, type="gateway_error").inc()
        raise
    except BaseException:
        await cm.__aexit__(None, None, None)
        raise


def provider_base_url(app: Any, provider: str) -> str:
    from ..providers import PROVIDERS

    return PROVIDERS[provider].base_url(app.state.settings)


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _error_response(status: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": error_type}}, status_code=status)


__all__ = ["run_proxy", "unmask_whole"]
