"""One JSON event per line on stdout. Stdlib only."""

from __future__ import annotations

import sys
from typing import TextIO

from ..schema import EvidenceEvent


class StdoutEmitter:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def emit(self, event: EvidenceEvent) -> None:
        self._stream.write(event.to_json() + "\n")
        self._stream.flush()

    def close(self) -> None:
        return None
