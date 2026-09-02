"""Session lifecycle for the gateway.

A *session* is a ``maskflow.Session`` -- the object that keeps
value->placeholder identity stable across turns and tool calls. The client
opts into one with an ``X-Maskflow-Session: <opaque id>`` header; with no
header, every request gets a fresh ephemeral session that is discarded
after the response.

Two backends:

* ``InProcessSessionStore`` -- a TTL dict. Fine for a single replica; a
  scaled-out deployment needs Redis or two replicas will disagree on what
  ``<PHONE_1>`` means.
* ``RedisSessionStore`` -- snapshots encrypted with AES-256-GCM
  (``MASKFLOW_GATEWAY_SESSION_KEY``) before they touch Redis, mandatory
  TTL, and a ``maxmemory-policy != noeviction`` check that fails ``/readyz``
  (eviction mid-conversation = failed unmask = raw placeholders to a user).
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from maskflow import RootConfig, Session

from .config import Settings
from .errors import SessionUnavailable

# The gateway's masking config comes from its own MASKFLOW_GATEWAY_* env
# (see config.Settings), never from a .maskflowrc -- pass an explicit empty
# RootConfig so Session skips filesystem discovery entirely.
_GATEWAY_CONFIG = RootConfig()


class SnapshotStore(Protocol):
    async def load(self, session_id: str) -> bytes | None: ...

    async def save(self, session_id: str, blob: bytes, ttl_seconds: int) -> None: ...

    async def delete(self, session_id: str) -> None: ...

    async def check_ready(self) -> None:
        """Raise SessionUnavailable if the backend is not safe to use."""

    async def aclose(self) -> None: ...

    @property
    def redis(self) -> object | None: ...


class InProcessSnapshotStore:
    """Process-local TTL dict. No encryption -- the bytes never leave the
    process. Not shared between replicas."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, bytes]] = {}

    async def load(self, session_id: str) -> bytes | None:
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        expires_at, blob = entry
        if time.monotonic() >= expires_at:
            self._entries.pop(session_id, None)
            return None
        return blob

    async def save(self, session_id: str, blob: bytes, ttl_seconds: int) -> None:
        self._entries[session_id] = (time.monotonic() + ttl_seconds, blob)

    async def delete(self, session_id: str) -> None:
        self._entries.pop(session_id, None)

    async def check_ready(self) -> None:
        return None

    async def aclose(self) -> None:
        self._entries.clear()

    @property
    def redis(self) -> None:
        return None


class RedisSnapshotStore:
    """AES-256-GCM-encrypted session snapshots in Redis, keyed
    ``maskflow:session:<id>`` with a mandatory TTL."""

    _KEY_PREFIX = "maskflow:session:"

    def __init__(
        self,
        url: str,
        key: bytes,
        *,
        require_noeviction: bool = True,
        redis_client: object | None = None,
    ) -> None:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "Redis sessions need 'cryptography' -- `pip install maskflow-gateway[redis]`."
            ) from exc

        if redis_client is not None:
            self._redis = redis_client
        else:
            try:
                from redis.asyncio import Redis
            except ImportError as exc:  # pragma: no cover - import guard
                raise RuntimeError(
                    "MASKFLOW_GATEWAY_REDIS_URL is set but the 'redis' extra is not "
                    "installed -- `pip install maskflow-gateway[redis]`."
                ) from exc
            self._redis = Redis.from_url(url)
        self._aesgcm = AESGCM(key)
        self._require_noeviction = require_noeviction

    def _key(self, session_id: str) -> str:
        return f"{self._KEY_PREFIX}{session_id}"

    async def load(self, session_id: str) -> bytes | None:
        blob = await self._redis.get(self._key(session_id))
        if blob is None:
            return None
        nonce, ciphertext = blob[:12], blob[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, None)

    async def save(self, session_id: str, blob: bytes, ttl_seconds: int) -> None:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, blob, None)
        await self._redis.set(self._key(session_id), nonce + ciphertext, ex=ttl_seconds)

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def check_ready(self) -> None:
        try:
            await self._redis.ping()
        except Exception as exc:  # noqa: BLE001 - surface any redis failure as 503
            raise SessionUnavailable(f"redis ping failed: {type(exc).__name__}") from exc
        if not self._require_noeviction:
            return
        try:
            policy = await self._redis.config_get("maxmemory-policy")
        except Exception:  # noqa: BLE001 - some managed Redis blocks CONFIG GET
            return
        value = (policy or {}).get("maxmemory-policy")
        if value and value != "noeviction":
            raise SessionUnavailable(
                f"redis maxmemory-policy is {value!r}, not 'noeviction' -- eviction "
                "would drop a live session and surface raw placeholders to a user"
            )

    async def aclose(self) -> None:
        await self._redis.aclose()

    @property
    def redis(self) -> object:
        return self._redis


def build_snapshot_store(settings: Settings) -> SnapshotStore:
    if settings.redis_url is None:
        return InProcessSnapshotStore()
    return RedisSnapshotStore(
        settings.redis_url,
        settings.require_session_key_bytes(),
        require_noeviction=settings.require_maxmemory_noeviction,
    )


class SessionManager:
    """Builds ``maskflow.Session`` objects with the gateway's masking config
    and moves their state to/from the snapshot store."""

    def __init__(self, store: SnapshotStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    def _new_session(self, ttl_seconds: int) -> Session:
        return Session(
            ttl_seconds=ttl_seconds,
            min_confidence=self._settings.min_confidence,
            patterns_only=not self._settings.ner,
            config=_GATEWAY_CONFIG,
        )

    def clamp_ttl(self, requested: int | None) -> int:
        ttl = requested if requested is not None else self._settings.session_ttl_seconds
        return max(1, min(ttl, self._settings.session_ttl_max_seconds))

    @asynccontextmanager
    async def use(
        self, session_id: str | None, *, ttl_seconds: int | None = None
    ) -> AsyncIterator[ManagedSession]:
        ttl = self.clamp_ttl(ttl_seconds)
        session = self._new_session(ttl)
        if session_id is not None:
            blob = await self._store.load(session_id)
            if blob is not None:
                session.restore(blob)
        managed = ManagedSession(session, session_id, ttl, self._store)
        try:
            yield managed
        finally:
            session.close()

    async def aclose(self) -> None:
        await self._store.aclose()


class ManagedSession:
    """One session for the duration of one request. ``persist()`` writes the
    current mapping back to the store (only meaningful for a keyed session);
    it must be called after request-side masking and before the upstream
    call, so a crash mid-stream never loses the mapping needed to unmask."""

    def __init__(
        self, session: Session, session_id: str | None, ttl_seconds: int, store: SnapshotStore
    ) -> None:
        self.session = session
        self.session_id = session_id
        self.ttl_seconds = ttl_seconds
        self._store = store

    @property
    def keyed(self) -> bool:
        return self.session_id is not None

    async def persist(self) -> None:
        if self.session_id is None:
            return
        await self._store.save(self.session_id, self.session.snapshot(), self.ttl_seconds)
