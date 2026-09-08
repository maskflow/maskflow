"""``EvidenceConfig`` -- the resolved settings :func:`build_emitter` needs,
plus the two ways to obtain it:

* :meth:`EvidenceConfig.from_rootconfig` -- from a ``maskflow_core`` resolved
  config's ``[evidence]`` section (the CLI path);
* :meth:`EvidenceConfig.from_env` -- from ``MASKFLOW_..._EVIDENCE_*``
  environment variables (the gateway path, which is env-only by design).

Evidence is **off by default** in both.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_SINKS = ("stdout", "file", "syslog", "webhook", "otlp")


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class EvidenceConfig:
    enabled: bool = False
    sink: str = "file"
    # file sink
    path: str = "evidence.log"
    max_bytes: int = 10_000_000
    backups: int = 5
    # webhook / otlp sink
    url: str = ""
    timeout: float = 2.0
    # syslog sink -- empty host means the local socket (/dev/log, or the
    # macOS equivalent), which is what most deployments want.
    syslog_host: str = ""
    syslog_port: int = 514
    # context stamped onto every event
    service: str = "maskflow"
    environment: str = "production"

    def __post_init__(self) -> None:
        if self.sink not in _SINKS:
            raise ValueError(f"[evidence] sink must be one of {_SINKS}, got {self.sink!r}")

    def syslog_address(self) -> str | tuple[str, int]:
        if self.syslog_host:
            return (self.syslog_host, self.syslog_port)
        return "/dev/log"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidenceConfig:
        base = cls()
        return cls(
            enabled=_as_bool(data.get("enabled"), base.enabled),
            sink=str(data.get("sink", base.sink)),
            path=str(data.get("path", base.path)),
            max_bytes=_as_int(data.get("max_bytes"), base.max_bytes),
            backups=_as_int(data.get("backups"), base.backups),
            url=str(data.get("url", base.url)),
            timeout=_as_float(data.get("timeout"), base.timeout),
            syslog_host=str(data.get("syslog_host", base.syslog_host)),
            syslog_port=_as_int(data.get("syslog_port"), base.syslog_port),
            service=str(data.get("service", base.service)),
            environment=str(data.get("environment", base.environment)),
        )

    @classmethod
    def from_rootconfig(cls, root_config: Any) -> EvidenceConfig:
        """Read the ``evidence`` section off a ``maskflow_core`` ``RootConfig``
        (or anything with a compatible ``.evidence`` attribute). A config with
        no ``[evidence]`` section yields the disabled default."""
        section = getattr(root_config, "evidence", None)
        if section is None:
            return cls()
        if isinstance(section, Mapping):
            return cls.from_dict(section)
        # a dataclass section -> pull known attributes
        keys = (
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
        return cls.from_dict({k: getattr(section, k) for k in keys if hasattr(section, k)})

    @classmethod
    def from_env(cls, prefix: str, env: Mapping[str, str] | None = None) -> EvidenceConfig:
        """Build from ``{prefix}ENABLED``, ``{prefix}SINK``, ... (e.g.
        ``prefix="MASKFLOW_GATEWAY_EVIDENCE_"``)."""
        source = env if env is not None else os.environ
        picked = {
            key[len(prefix) :].lower(): value
            for key, value in source.items()
            if key.startswith(prefix)
        }
        return cls.from_dict(picked)
