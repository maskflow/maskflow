from __future__ import annotations

import os

import pytest
from fakeredis import FakeAsyncRedis
from maskflow_gateway.config import Settings
from maskflow_gateway.errors import SessionUnavailable
from maskflow_gateway.sessions import (
    InProcessSnapshotStore,
    RedisSnapshotStore,
    SessionManager,
)

EMAIL = "alice@example.com"

# Explicit so these pass regardless of which pyproject's `asyncio_mode`
# pytest picks up (the gateway's is `auto`, but a multi-package invocation
# resolves config at the repo root instead).
pytestmark = pytest.mark.asyncio


@pytest.fixture
def manager_settings() -> Settings:
    return Settings(redis_url=None, ner=False, _env_file=None)  # type: ignore[call-arg]


async def test_in_process_ephemeral_session_has_no_id(manager_settings: Settings) -> None:
    mgr = SessionManager(InProcessSnapshotStore(), manager_settings)
    async with mgr.use(None) as managed:
        assert managed.keyed is False
        out = managed.session.mask(f"mail {EMAIL}")
        assert EMAIL not in out
        await managed.persist()  # no-op for an unkeyed session


async def test_keyed_session_round_trips_across_two_uses(manager_settings: Settings) -> None:
    store = InProcessSnapshotStore()
    mgr = SessionManager(store, manager_settings)

    async with mgr.use("sess-1") as first:
        masked = first.session.mask(f"mail {EMAIL}")
        await first.persist()

    async with mgr.use("sess-1") as second:
        # identity preserved: same value -> same token as the first use
        assert second.session.mask(f"again {EMAIL}") == masked.replace("mail", "again")
        assert second.session.unmask(masked) == f"mail {EMAIL}"


async def test_ttl_is_clamped_to_max(manager_settings: Settings) -> None:
    mgr = SessionManager(InProcessSnapshotStore(), manager_settings)
    assert mgr.clamp_ttl(10**9) == manager_settings.session_ttl_max_seconds
    assert mgr.clamp_ttl(None) == manager_settings.session_ttl_seconds
    assert mgr.clamp_ttl(-5) == 1


async def test_redis_store_encrypts_at_rest() -> None:
    fake = FakeAsyncRedis()
    key = os.urandom(32)
    store = RedisSnapshotStore("redis://x", key, redis_client=fake)
    await store.save("s1", b'{"v":1,"secret":"alice@example.com"}', ttl_seconds=60)

    raw = await fake.get("maskflow:session:s1")
    assert b"alice@example.com" not in raw  # ciphertext, not plaintext
    assert await store.load("s1") == b'{"v":1,"secret":"alice@example.com"}'
    assert await store.load("missing") is None


async def test_redis_ttl_is_set() -> None:
    fake = FakeAsyncRedis()
    store = RedisSnapshotStore("redis://x", os.urandom(32), redis_client=fake)
    await store.save("s1", b"blob", ttl_seconds=42)
    assert 0 < await fake.ttl("maskflow:session:s1") <= 42


class _PolicyRedis:
    """Minimal stub: fakeredis doesn't implement CONFIG GET."""

    def __init__(self, policy: str) -> None:
        self._policy = policy

    async def ping(self) -> bool:
        return True

    async def config_get(self, _pattern: str) -> dict[str, str]:
        return {"maxmemory-policy": self._policy}


async def test_readyz_fails_closed_on_bad_maxmemory_policy() -> None:
    store = RedisSnapshotStore(
        "redis://x", os.urandom(32), redis_client=_PolicyRedis("allkeys-lru")
    )
    with pytest.raises(SessionUnavailable, match="noeviction"):
        await store.check_ready()


async def test_readyz_ok_when_noeviction() -> None:
    store = RedisSnapshotStore("redis://x", os.urandom(32), redis_client=_PolicyRedis("noeviction"))
    await store.check_ready()  # must not raise
