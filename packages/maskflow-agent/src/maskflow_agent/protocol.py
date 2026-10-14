"""Client side of the daemon protocol: one JSON request line, one JSON
response line, per connection over a unix socket. Stdlib only.

Errors raise `DaemonUnavailable` with a fixed message -- never request
content, which may hold PII.
"""

from __future__ import annotations

import errno
import json
import socket
import time
from typing import Any

from . import paths

# Generous: a 10 MB Read through spaCy can take a while. Hooks have their own
# outer timeout configured at install time.
DEFAULT_TIMEOUT = 120.0
_MAX_RESPONSE = 256 * 1024 * 1024


class DaemonUnavailable(Exception):
    """The session's daemon isn't running or didn't answer properly."""


# A busy daemon's accept queue can briefly be full when many hooks fire at
# once; Linux then fails the connect immediately (EAGAIN) instead of waiting.
_CONNECT_RETRY_SECONDS = 2.0
_BUSY = (errno.EAGAIN, errno.EWOULDBLOCK, errno.ECONNREFUSED)


def _connect(path: str, timeout: float) -> socket.socket:
    deadline = time.monotonic() + min(_CONNECT_RETRY_SECONDS, timeout)
    delay = 0.01
    while True:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(path)
            return sock
        except OSError as exc:
            sock.close()
            # A missing socket file means no daemon: fail fast, don't retry.
            if exc.errno not in _BUSY or time.monotonic() + delay > deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.2)


def request(
    session_id: str, op: str, timeout: float = DEFAULT_TIMEOUT, **fields: Any
) -> dict[str, Any]:
    path = paths.socket_path(session_id)
    payload = json.dumps({"op": op, **fields}, ensure_ascii=False).encode("utf-8") + b"\n"
    try:
        with _connect(str(path), timeout) as sock:
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = sock.recv(1 << 16)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_RESPONSE:
                    raise DaemonUnavailable("daemon response too large")
                chunks.append(chunk)
    except (OSError, ValueError) as exc:
        raise DaemonUnavailable(f"daemon not reachable ({type(exc).__name__})") from None
    try:
        response = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DaemonUnavailable("daemon sent an unreadable response") from None
    if not isinstance(response, dict) or not response.get("ok"):
        error = response.get("error", "unknown") if isinstance(response, dict) else "unknown"
        raise DaemonUnavailable(f"daemon error: {error}")
    return response


def ping(session_id: str, timeout: float = 2.0) -> bool:
    try:
        request(session_id, "ping", timeout=timeout)
    except DaemonUnavailable:
        return False
    return True
