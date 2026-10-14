"""Where the per-session daemon lives. Stdlib only.

`MASKFLOW_AGENT_HOME` (default `~/.maskflow/agent`) holds one unix socket and
one log per live session, plus counts-only session summaries. The directory
is created 0700 so other local users can't reach a socket.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")
# AF_UNIX paths are limited to ~104 bytes on macOS; keep ours well under.
_MAX_ID = 64


@lru_cache(maxsize=1)
def home() -> Path:
    """Resolved once per process: the daemon strips MASKFLOW_AGENT_* from its
    environment before loading the engine (core's config loader rejects
    unknown MASKFLOW_* variables), after this has been read."""
    root = Path(os.environ.get("MASKFLOW_AGENT_HOME") or Path.home() / ".maskflow" / "agent")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def safe_id(session_id: str) -> str:
    cleaned = _SAFE_ID.sub("_", session_id)[:_MAX_ID]
    if not cleaned or cleaned.strip("._") == "":
        raise ValueError("unusable session id")
    return cleaned


# macOS caps AF_UNIX paths at 104 bytes (Linux 108).
_MAX_SOCKET_PATH = 100


@lru_cache(maxsize=1)
def _socket_dir() -> Path:
    if len(str(home())) + 1 + _MAX_ID + 5 <= _MAX_SOCKET_PATH:
        return home()
    short = Path("/tmp") / f"maskflow-agent-{os.getuid()}"
    short.mkdir(exist_ok=True, mode=0o700)
    if short.stat().st_uid != os.getuid():
        raise PermissionError("socket directory owned by another user")
    os.chmod(short, 0o700)
    return short


def socket_path(session_id: str) -> Path:
    return _socket_dir() / f"{safe_id(session_id)}.sock"


def log_path(session_id: str) -> Path:
    return home() / f"{safe_id(session_id)}.log"


def summary_path(session_id: str) -> Path:
    sessions = home() / "sessions"
    sessions.mkdir(exist_ok=True, mode=0o700)
    return sessions / f"{safe_id(session_id)}.json"
