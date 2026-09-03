"""Session lifecycle for the LiteLLM guardrail.

A *session* is a ``maskflow.Session`` -- the object that keeps
value -> placeholder identity stable across turns and tool calls. Two
lifetimes:

* **Ephemeral** -- no session id on the request. One session per request,
  keyed by ``litellm_call_id`` so ``async_pre_call_hook`` (mask) and
  ``async_post_call_success_hook`` / the streaming hook (unmask) share it,
  then discarded. Always in-process: LiteLLM runs both hooks for one
  request in one worker.
* **Keyed** -- the client sent ``X-Maskflow-Session: <id>`` (or a
  ``maskflow_session_id`` metadata field). Token identity is stable across
  requests for ``ttl_seconds``. In-process by default (correct for a
  single-worker proxy); back it with Redis when the same id must resolve on
  another worker or replica.

Nothing here logs a mapping or an original value. ``InProcessSessionStore``
holds live ``Session`` objects in memory only. ``RedisSessionStore``
encrypts each snapshot with AES-256-GCM before it touches Redis and always
sets a TTL.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any, Protocol

from maskflow import Session


class SessionStore(Protocol):
    async def open(self, ref: str, ttl_seconds: int) -> Session:
        """Return the session for ``ref``, restoring prior masking state if
        the ref is known, otherwise a fresh one."""

    async def persist(self, ref: str, session: Session, ttl_seconds: int) -> None:
        """Save the session's current state under ``ref`` (and refresh TTL)."""

    async def discard(self, ref: str, session: Session) -> None:
        """Forget ``ref`` and close its session (used for ephemeral refs)."""

    async def aclose(self) -> None: ...


class InProcessSessionStore:
    """Process-local TTL dict of live ``Session`` objects. No serialization,
    no encryption -- the mapping never leaves the process."""

    def __init__(self, session_factory: Callable[[int], Session]) -> None:
        self._factory = session_factory
        self._entries: dict[str, tuple[float, Session]] = {}

    def _sweep(self) -> None:
        now = time.monotonic()
        for ref in [r for r, (exp, _) in self._entries.items() if exp <= now]:
            _, session = self._entries.pop(ref)
            session.close()

    async def open(self, ref: str, ttl_seconds: int) -> Session:
        self._sweep()
        entry = self._entries.get(ref)
        if entry is not None and entry[0] > time.monotonic():
            return entry[1]
        if entry is not None:
            entry[1].close()
        session = self._factory(ttl_seconds)
        self._entries[ref] = (time.monotonic() + ttl_seconds, session)
        return session

    async def persist(self, ref: str, session: Session, ttl_seconds: int) -> None:
        self._entries[ref] = (time.monotonic() + ttl_seconds, session)

    async def discard(self, ref: str, session: Session) -> None:
        self._entries.pop(ref, None)
        session.close()

    async def aclose(self) -> None:
        for _, session in self._entries.values():
            session.close()
        self._entries.clear()


class RedisSessionStore:
    """AES-256-GCM-encrypted ``Session.snapshot()`` blobs in Redis, keyed
    ``maskflow:litellm:session:<ref>`` with a mandatory TTL. Used for keyed
    (cross-turn) sessions on a multi-worker / multi-replica proxy.

    Ephemeral refs still go through the in-process store the guardrail also
    holds -- a single request's mask and unmask always run in one worker, so
    there is nothing to share for them.
    """

    _KEY_PREFIX = "maskflow:litellm:session:"

    def __init__(
        self,
        url: str,
        key: bytes,
        session_factory: Callable[[int], Session],
        *,
        redis_client: Any | None = None,
    ) -> None:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "Redis sessions need 'cryptography' -- `pip install maskflow-litellm[redis]`."
            ) from exc
        if len(key) not in (16, 24, 32):
            raise ValueError(
                "maskflow_session_encryption_key must decode to 16, 24, or 32 bytes "
                "(AES-128/192/256)."
            )

        self._factory = session_factory
        self._aesgcm = AESGCM(key)
        self._redis: Any
        if redis_client is not None:
            self._redis = redis_client
        else:
            try:
                from redis.asyncio import Redis
            except ImportError as exc:  # pragma: no cover - import guard
                raise RuntimeError(
                    "maskflow_redis_url is set but the 'redis' extra is not installed -- "
                    "`pip install maskflow-litellm[redis]`."
                ) from exc
            self._redis = Redis.from_url(url)

    def _key(self, ref: str) -> str:
        return f"{self._KEY_PREFIX}{ref}"

    async def open(self, ref: str, ttl_seconds: int) -> Session:
        session = self._factory(ttl_seconds)
        blob = await self._redis.get(self._key(ref))
        if blob is not None:
            nonce, ciphertext = blob[:12], blob[12:]
            session.restore(self._aesgcm.decrypt(nonce, ciphertext, None))
        return session

    async def persist(self, ref: str, session: Session, ttl_seconds: int) -> None:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, session.snapshot(), None)
        await self._redis.set(self._key(ref), nonce + ciphertext, ex=ttl_seconds)

    async def discard(self, ref: str, session: Session) -> None:
        await self._redis.delete(self._key(ref))
        session.close()

    async def aclose(self) -> None:
        aclose = getattr(self._redis, "aclose", None)
        if aclose is not None:
            await aclose()
