"""Constants and small utilities shared across the gateway test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator

OPENAI_BASE = "https://upstream.test/openai/v1"
ANTHROPIC_BASE = "https://upstream.test/anthropic/v1"


def byte_chunks(*parts: str) -> AsyncIterator[bytes]:
    """An async byte iterator over `parts` -- for feeding a mocked SSE
    response body through httpx with controlled chunk boundaries."""

    async def gen() -> AsyncIterator[bytes]:
        for part in parts:
            yield part.encode("utf-8")

    return gen()
