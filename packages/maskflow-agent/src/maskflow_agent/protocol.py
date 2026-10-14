"""Client side of the daemon protocol: one JSON request line, one JSON
response line, per connection over a unix socket. Stdlib only.

Errors raise `DaemonUnavailable` with a fixed message -- never request
content, which may hold PII.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from . import paths

# Generous: a 10 MB Read through spaCy can take a while. Hooks have their own
# outer timeout configured at install time.
DEFAULT_TIMEOUT = 120.0
_MAX_RESPONSE = 256 * 1024 * 1024


class DaemonUnavailable(Exception):
    """The session's daemon isn't running or didn't answer properly."""


def request(
    session_id: str, op: str, timeout: float = DEFAULT_TIMEOUT, **fields: Any
) -> dict[str, Any]:
    path = paths.socket_path(session_id)
    payload = json.dumps({"op": op, **fields}, ensure_ascii=False).encode("utf-8") + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
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
