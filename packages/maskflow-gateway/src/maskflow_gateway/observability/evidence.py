"""Evidence emission for the gateway.

When ``[evidence]`` is enabled (in a discoverable ``.maskflowrc``, or via
``MASKFLOW_GATEWAY_EVIDENCE_*`` env vars which win), every proxied request
emits one metadata-only :class:`~maskflow_evidence.EvidenceEvent` per
detected entity type -- never a value. Off by default.

Emission is best-effort: a bad model string or a broken sink is logged and
dropped, never propagated into the proxy flow.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable

from maskflow_core import Mapping
from maskflow_evidence import (
    EventContext,
    EvidenceConfig,
    build_emitter,
    events_from_mapping,
)
from maskflow_evidence.emitters import Emitter, NullEmitter

from . import metrics

logger = logging.getLogger("maskflow_gateway.evidence")

_ENV_PREFIX = "MASKFLOW_GATEWAY_EVIDENCE_"
# What EvidenceEvent accepts for a slug field; anything else we coarsen or drop.
_SLUG_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:-]{0,63}$")


def _resolve_config() -> EvidenceConfig:
    """`.maskflowrc` `[evidence]` as the base, `MASKFLOW_GATEWAY_EVIDENCE_*`
    env vars overlaid on top."""
    base = EvidenceConfig()
    try:
        from maskflow_core.config import resolve_config

        base = EvidenceConfig.from_rootconfig(resolve_config().config)
    except Exception:  # noqa: BLE001 - a broken rc must not stop the gateway
        logger.warning("could not read .maskflowrc [evidence]; using defaults", exc_info=True)

    env = EvidenceConfig.from_env(_ENV_PREFIX)
    if env == EvidenceConfig():
        return base
    # env overlay: take any field the env actually set (i.e. differs from default)
    default = EvidenceConfig()
    merged = {
        f: getattr(env if getattr(env, f) != getattr(default, f) else base, f)
        for f in (
            "enabled",
            "sink",
            "path",
            "max_bytes",
            "backups",
            "url",
            "timeout",
            "syslog_host",
            "syslog_port",
            "service",
            "environment",
        )
    }
    return EvidenceConfig(**merged)


class GatewayEvidence:
    """Holds the process-wide emitter and the static context fields."""

    def __init__(self, emitter: Emitter, config: EvidenceConfig) -> None:
        self._emitter = emitter
        self._service = config.service if _SLUG_OK.match(config.service) else "maskflow"
        self._environment = (
            config.environment if _SLUG_OK.match(config.environment) else "production"
        )
        self.enabled = not isinstance(emitter, NullEmitter)
        self.sink = config.sink if self.enabled else "none"

    @classmethod
    def from_config(cls, config: EvidenceConfig | None = None) -> GatewayEvidence:
        config = config or _resolve_config()
        return cls(build_emitter(config), config)

    def emit_request(
        self,
        mapping: Mapping,
        new_tokens: Iterable[str],
        *,
        provider: str,
        model: str | None,
        raw_session_id: str | None,
    ) -> int:
        """Emit one event per (entity_type, recognizer) for the tokens added
        by this request. Returns the number of events emitted (0 when
        disabled or nothing was detected)."""
        if not self.enabled:
            return 0
        tokens = list(new_tokens)
        if not tokens:
            return 0
        try:
            ctx = EventContext(
                session_id=_session_slug(raw_session_id),
                service=self._service,
                environment=self._environment,
                provider=provider if _SLUG_OK.match(provider) else None,
                model=model if (model and _SLUG_OK.match(model)) else None,
            )
            events = events_from_mapping(mapping, ctx, only_tokens=tokens)
            for event in events:
                self._emitter.emit(event)
            if events:
                metrics.EVIDENCE_EMITTED.labels(sink=self.sink).inc(len(events))
            return len(events)
        except Exception:  # noqa: BLE001 - evidence must never break a proxied request
            logger.warning("evidence emission failed for a request", exc_info=True)
            return 0

    def close(self) -> None:
        self._emitter.close()


def _session_slug(raw: str | None) -> str:
    """A stable, opaque id for the event. A client session header is hashed
    (never emitted raw -- it could be anything); absent, a per-process
    marker plus a short random tail keeps events groupable without
    identifying anyone."""
    if raw:
        return "s_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return "s_anon_" + hashlib.sha256(b"maskflow-gateway").hexdigest()[:16]
