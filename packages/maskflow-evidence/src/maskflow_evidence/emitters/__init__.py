"""Emitters: one interface, several self-hosted backends, off by default.

Every backend is a :class:`Emitter`. Nothing here phones home -- ``stdout``,
``file`` and ``syslog`` are stdlib; ``webhook`` POSTs to a URL you configure;
``otlp`` ships to an OpenTelemetry collector you run. The default everywhere
is :class:`NullEmitter`.

An emit failure is never fatal: :class:`SafeEmitter` wraps every real
backend so a broken sink drops the event (and bumps a counter) rather than
breaking the masking call that produced it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..schema import EvidenceEvent

if TYPE_CHECKING:
    from ..config import EvidenceConfig

_log = logging.getLogger("maskflow.evidence")


@runtime_checkable
class Emitter(Protocol):
    def emit(self, event: EvidenceEvent) -> None: ...
    def close(self) -> None: ...


class NullEmitter:
    """Does nothing. The default -- evidence is opt-in."""

    def emit(self, event: EvidenceEvent) -> None:  # noqa: D102
        return None

    def close(self) -> None:  # noqa: D102
        return None


class SafeEmitter:
    """Wraps a backend so ``emit`` never raises into the caller. Drop count
    is readable via :attr:`dropped` (the gateway surfaces it as a metric)."""

    def __init__(self, inner: Emitter) -> None:
        self._inner = inner
        self.dropped = 0

    def emit(self, event: EvidenceEvent) -> None:
        try:
            self._inner.emit(event)
        except Exception:  # noqa: BLE001 -- evidence must never break masking
            self.dropped += 1
            _log.warning("evidence emit failed; event dropped", exc_info=True)

    def close(self) -> None:
        try:
            self._inner.close()
        except Exception:  # noqa: BLE001
            _log.warning("evidence emitter close failed", exc_info=True)


def build_emitter(config: EvidenceConfig) -> Emitter:
    """Construct the emitter described by ``config``. Returns a
    :class:`NullEmitter` when evidence is disabled. Real backends are wrapped
    in :class:`SafeEmitter`."""
    if not config.enabled:
        return NullEmitter()

    sink = config.sink
    if sink == "stdout":
        from .stdout import StdoutEmitter

        return SafeEmitter(StdoutEmitter())
    if sink == "file":
        from .file import FileEmitter

        return SafeEmitter(
            FileEmitter(config.path, max_bytes=config.max_bytes, backups=config.backups)
        )
    if sink == "syslog":
        from .syslog import SyslogEmitter

        return SafeEmitter(SyslogEmitter(config.syslog_address()))
    if sink == "webhook":
        from .webhook import WebhookEmitter

        return SafeEmitter(WebhookEmitter(config.url, timeout=config.timeout))
    if sink == "otlp":
        from .otlp import OTLPEmitter

        return SafeEmitter(OTLPEmitter(config.url))

    raise ValueError(f"unknown evidence sink {sink!r}")


__all__ = ["Emitter", "NullEmitter", "SafeEmitter", "build_emitter"]
