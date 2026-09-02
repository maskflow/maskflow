"""Structured logging with a hard PII scrub.

Two layers of defence for CLAUDE.md rule 1:

1. Every log record's formatted message goes through
   ``maskflow_core``'s ``PIIRedactionFilter`` (pattern/checksum pass) before
   emission -- so even a mistaken ``logger.info(user_text)`` somewhere is
   scrubbed.
2. The gateway's own log calls never pass raw request/response bodies in
   the first place -- only counts, entity types, durations, status codes.

JSON output by default (one object per line) for ingestion; plain text
when ``MASKFLOW_GATEWAY_JSON_LOGS=0`` for local dev.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from maskflow_core import install_pii_filter

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, json_logs: bool = True, level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)

    # Layer 1: scrub every record that flows through the root logger.
    install_pii_filter(root)

    # uvicorn's access log is noisy and can echo query strings -- let our
    # own request-completion log line be the record of truth.
    logging.getLogger("uvicorn.access").disabled = True
