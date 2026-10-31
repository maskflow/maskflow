"""What one intercepted request looks like.

The payload is held so the escape detector can search it, and is
repr-excluded: it is the audited application's real outbound traffic, which
during a seeded run contains canaries and may also contain whatever else
that application handles. Nothing but canary values is ever rendered out of
this object.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StackFrame:
    """One frame of the Python stack at the moment the request was sent.

    Identifiers only: file, line, function. Never the source line, and
    never a local variable.
    """

    file: str
    line: int
    function: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} in {self.function}"


@dataclass(frozen=True)
class Capture:
    """One outbound request the audit stopped before it left the process."""

    host: str
    method: str
    url: str = field(repr=False)  # may carry query parameters
    payload: str = field(repr=False)  # the request body
    library: str  # httpx | requests | aiohttp | urllib
    stack: tuple[StackFrame, ...] = ()

    def app_frames(self, root: str) -> tuple[StackFrame, ...]:
        """Frames inside the audited tree, innermost last.

        The raw stack is mostly SDK internals -- twenty frames of openai
        and httpx before anything the user wrote. The useful answer is the
        deepest frame that belongs to the project, which is what the
        report quotes as the leaking line.
        """
        return tuple(f for f in self.stack if f.file.startswith(root))


class CaptureStore:
    """Thread-safe collector. The interceptor writes, the audit reads.

    Locked because a real test suite sends requests from worker threads
    and an async event loop, and a dropped capture is a missed leak.
    """

    def __init__(self) -> None:
        self._captures: list[Capture] = []
        self._lock = threading.Lock()

    def add(self, capture: Capture) -> None:
        with self._lock:
            self._captures.append(capture)

    @property
    def captures(self) -> tuple[Capture, ...]:
        with self._lock:
            return tuple(self._captures)

    def __len__(self) -> int:
        with self._lock:
            return len(self._captures)

    def clear(self) -> None:
        with self._lock:
            self._captures.clear()
