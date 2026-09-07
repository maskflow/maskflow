"""Append events to a size-rotated JSON-lines file. Stdlib only.

Uses ``logging.handlers.RotatingFileHandler`` for the rotation mechanics
(byte cap, N backups) without routing through the logging tree -- the
handler is driven directly so evidence output never mixes with app logs and
is not affected by log-level config.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..schema import EvidenceEvent


class FileEmitter:
    def __init__(self, path: str | Path, *, max_bytes: int = 10_000_000, backups: int = 5) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handler = RotatingFileHandler(
            self._path,
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
            delay=True,
        )
        self._handler.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, event: EvidenceEvent) -> None:
        record = logging.LogRecord(
            name="maskflow.evidence",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg=event.to_json(),
            args=(),
            exc_info=None,
        )
        self._handler.emit(record)

    def close(self) -> None:
        self._handler.close()
