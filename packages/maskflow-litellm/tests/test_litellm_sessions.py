"""Session stores: in-process TTL dict and the AES-GCM Redis backend."""

from __future__ import annotations

import os

import maskflow
import pytest
from maskflow_litellm._sessions import InProcessSessionStore, RedisSessionStore


def _factory(ttl: int) -> maskflow.Session:
    return maskflow.Session(ttl_seconds=ttl, config=maskflow.RootConfig())


@pytest.mark.asyncio
async def test_inprocess_same_ref_returns_same_live_session() -> None:
    store = InProcessSessionStore(_factory)
    s1 = await store.open("s:conv-1", 60)
    s1.mask("PAN ABCPE1234F")
    s2 = await store.open("s:conv-1", 60)
    assert s2 is s1
    assert "<PAN_1>" in s2.mask("again PAN ABCPE1234F")
    await store.aclose()


@pytest.mark.asyncio
async def test_inprocess_discard_closes_and_forgets() -> None:
    store = InProcessSessionStore(_factory)
    s1 = await store.open("c:call-1", 60)
    await store.discard("c:call-1", s1)
    with pytest.raises(maskflow.SessionClosedError):
        s1.mask("x")
    s2 = await store.open("c:call-1", 60)
    assert s2 is not s1
    await store.aclose()


@pytest.mark.asyncio
async def test_redis_store_round_trips_encrypted_snapshot() -> None:
    fakeredis = pytest.importorskip("fakeredis")
    redis = fakeredis.aioredis.FakeRedis()
    key = os.urandom(32)

    store = RedisSessionStore("redis://x", key, _factory, redis_client=redis)
    s1 = await store.open("s:conv-9", 60)
    masked = s1.mask("email alice@example.com")
    await store.persist("s:conv-9", s1, 60)

    # stored bytes must not contain the plaintext original
    raw = await redis.get("maskflow:litellm:session:s:conv-9")
    assert b"alice@example.com" not in raw

    store2 = RedisSessionStore("redis://x", key, _factory, redis_client=redis)
    s2 = await store2.open("s:conv-9", 60)
    assert s2.mask("email alice@example.com") == masked  # same token, restored mapping
    assert s2.unmask(masked) == "email alice@example.com"


@pytest.mark.asyncio
async def test_redis_store_rejects_bad_key_length() -> None:
    with pytest.raises(ValueError, match="16, 24, or 32"):
        RedisSessionStore("redis://x", b"short", _factory, redis_client=object())
