"""Ship events to a syslog daemon via ``logging.handlers.SysLogHandler``.
Stdlib only. Address is either a ``(host, port)`` pair or a local socket
path (e.g. ``/dev/log``)."""

from __future__ import annotations

import logging
from logging.handlers import SysLogHandler

from ..schema import EvidenceEvent


class SyslogEmitter:
    def __init__(self, address: str | tuple[str, int]) -> None:
        self._handler = SysLogHandler(address=address)
        self._handler.setFormatter(logging.Formatter("maskflow-evidence: %(message)s"))

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
