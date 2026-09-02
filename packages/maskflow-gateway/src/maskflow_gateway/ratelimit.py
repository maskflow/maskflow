"""Per-API-key rate limiting.

Keyed by a SHA-256 of the client's ``Authorization`` / ``x-api-key`` header
(never the raw key). Token-bucket semantics: a bucket of
``rate_limit_burst`` tokens refilled at ``rate_limit_per_minute / 60`` per
second.

Backed by Redis when configured (correct across replicas) or an in-process
dict otherwise (per-replica -- documented in the deploy notes).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from .config import Settings


def client_key(headers: Any) -> str:
    raw = headers.get("authorization") or headers.get("x-api-key") or "anonymous"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, tokens: float, updated: float) -> None:
        self.tokens = tokens
        self.updated = updated


class RateLimiter:
    def __init__(self, settings: Settings, redis: Any | None = None) -> None:
        self._per_minute = settings.rate_limit_per_minute
        self._burst = float(settings.effective_rate_limit_burst() or 1)
        self._refill_per_sec = self._per_minute / 60.0
        self._redis = redis
        self._buckets: dict[str, _Bucket] = {}

    @property
    def enabled(self) -> bool:
        return self._per_minute > 0

    async def check(self, key: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        if not self.enabled:
            return True, 0.0
        if self._redis is not None:
            return await self._check_redis(key)
        return self._check_local(key)

    def _check_local(self, key: str) -> tuple[bool, float]:
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(self._burst, now)
            self._buckets[key] = bucket
        bucket.tokens = min(
            self._burst, bucket.tokens + (now - bucket.updated) * self._refill_per_sec
        )
        bucket.updated = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True, 0.0
        return False, (1.0 - bucket.tokens) / self._refill_per_sec

    async def _check_redis(self, key: str) -> tuple[bool, float]:
        # Fixed-window counter -- coarser than a true bucket but replica-safe
        # and Lua-free. Window is one minute.
        window = int(time.time()) // 60
        redis_key = f"maskflow:rl:{key}:{window}"
        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, 90)
        if count <= self._per_minute:
            return True, 0.0
        return False, 60 - (int(time.time()) % 60)
