"""One ``maskflow.Session`` per MCP client connection, so ``<PERSON_NAME_1>``
means the same person across every tool call in an agent run.

stdio: one connection for the proxy's lifetime, one session. HTTP: one per
``Mcp-Session-Id``. Sessions are held in memory only (the mapping is raw
PII) and swept on a lazy TTL, same as the SDK's ``InMemoryMappingStore``.
"""

from __future__ import annotations

import threading
import time

from maskflow import RootConfig, Session

# Masking config comes from CLI flags, never a filesystem .maskflowrc.
_CONFIG = RootConfig()


class SessionRegistry:
    def __init__(
        self,
        *,
        min_confidence: float | None = None,
        patterns_only: bool = False,
        ttl_seconds: float = 3600,
    ) -> None:
        self._min_confidence = min_confidence
        self._patterns_only = patterns_only
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, Session]] = {}
        self._lock = threading.Lock()

    def _new(self) -> Session:
        kwargs: dict[str, object] = {
            "ttl_seconds": None,
            "config": _CONFIG,
            "patterns_only": self._patterns_only,
        }
        if self._min_confidence is not None:
            kwargs["min_confidence"] = self._min_confidence
        return Session(**kwargs)  # type: ignore[arg-type]

    def _sweep(self, now: float) -> None:
        for key in [k for k, (exp, _) in self._entries.items() if exp <= now]:
            _, session = self._entries.pop(key)
            session.close()

    def get(self, key: str) -> Session:
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            entry = self._entries.get(key)
            if entry is not None and entry[0] > now:
                self._entries[key] = (now + self._ttl, entry[1])
                return entry[1]
            if entry is not None:
                entry[1].close()
            session = self._new()
            self._entries[key] = (now + self._ttl, session)
            return session

    def discard(self, key: str) -> None:
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry is not None:
            entry[1].close()

    def close(self) -> None:
        with self._lock:
            for _, session in self._entries.values():
                session.close()
            self._entries.clear()
