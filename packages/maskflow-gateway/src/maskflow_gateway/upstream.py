"""Thin async HTTP client for whatever provider endpoint sits behind the
gateway. No vendor SDKs -- one httpx client, connection-pooled, with
explicit connect/read timeouts.

Credential handling: by default the client's own auth headers
(``authorization``, ``x-api-key``) are forwarded untouched and the gateway
stores nothing. If ``MASKFLOW_GATEWAY_UPSTREAM_API_KEY`` is set, it
replaces them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx

from .config import Settings
from .errors import UpstreamError

# Never forwarded upstream (hop-by-hop, or set by httpx itself).
_DROP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-authorization",
    "transfer-encoding",
    "upgrade",
    "te",
    "trailer",
    "accept-encoding",
    "x-maskflow-session",
    "x-maskflow-session-ttl",
}
_DROP_RESPONSE_HEADERS = {
    "content-length",
    "content-encoding",
    "transfer-encoding",
    "connection",
    "keep-alive",
}


def forward_request_headers(incoming: Mapping[str, str], settings: Settings) -> dict[str, str]:
    headers = {k: v for k, v in incoming.items() if k.lower() not in _DROP_REQUEST_HEADERS}
    if settings.upstream_api_key is not None:
        key = settings.upstream_api_key.get_secret_value()
        headers.pop("authorization", None)
        headers.pop("Authorization", None)
        headers["authorization"] = f"Bearer {key}"
        if "x-api-key" in {k.lower() for k in headers}:
            headers = {k: v for k, v in headers.items() if k.lower() != "x-api-key"}
            headers["x-api-key"] = key
    return headers


def filter_response_headers(response: httpx.Response) -> dict[str, str]:
    return {k: v for k, v in response.headers.items() if k.lower() not in _DROP_RESPONSE_HEADERS}


class Upstream:
    def __init__(self, settings: Settings) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.upstream_timeout_seconds,
                connect=settings.upstream_connect_timeout_seconds,
            ),
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def post_json(
        self, url: str, headers: Mapping[str, str], body: dict[str, Any]
    ) -> httpx.Response:
        try:
            return await self._client.post(url, headers=dict(headers), json=body)
        except httpx.TimeoutException as exc:
            raise UpstreamError("upstream timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"upstream connection error: {type(exc).__name__}") from exc

    @asynccontextmanager
    async def stream_json(
        self, url: str, headers: Mapping[str, str], body: dict[str, Any]
    ) -> AsyncIterator[httpx.Response]:
        try:
            async with self._client.stream(
                "POST", url, headers=dict(headers), json=body
            ) as response:
                yield response
        except httpx.TimeoutException as exc:
            raise UpstreamError("upstream timeout", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"upstream connection error: {type(exc).__name__}") from exc
