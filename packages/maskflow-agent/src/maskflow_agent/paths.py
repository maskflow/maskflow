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


def pid_path(session_id: str) -> Path:
    return home() / f"{safe_id(session_id)}.pid"


def start_lock_path(session_id: str) -> Path:
    return home() / f"{safe_id(session_id)}.start.lock"


def live_pid(session_id: str) -> int | None:
    """PID of a daemon process for this session that is still alive (running
    or still loading the engine), else None."""
    try:
        pid = int(pid_path(session_id).read_text().strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return None
    return pid


def log_path(session_id: str) -> Path:
    return home() / f"{safe_id(session_id)}.log"


def summary_path(session_id: str) -> Path:
    sessions = home() / "sessions"
    sessions.mkdir(exist_ok=True, mode=0o700)
    return sessions / f"{safe_id(session_id)}.json"


STALE_AFTER_SECONDS = 7 * 24 * 3600
_SESSION_FILE_SUFFIXES = (".start.lock", ".log", ".pid")


def remove_session_files(session_id: str, keep_log: bool) -> None:
    """A session's own leftovers after a clean shutdown: its start lock, and
    its log unless it holds warnings or errors worth keeping. The counts-only
    summary under sessions/ is the intended record and is kept."""
    lock = start_lock_path(session_id)
    try:
        import fcntl

        with open(lock, "a") as fh:
            # Only if no hook is mid-start holding it; a hook that opens it
            # after this unlink is still covered by the pid-file check.
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock.unlink(missing_ok=True)
    except OSError:
        pass
    if not keep_log:
        log_path(session_id).unlink(missing_ok=True)


def sweep_stale(now: float | None = None) -> int:
    """Remove lock/log/pid files of sessions that ended without a clean
    shutdown (killed, crashed): older than STALE_AFTER_SECONDS and with no
    live daemon. Returns how many files were removed."""
    import time

    cutoff = (time.time() if now is None else now) - STALE_AFTER_SECONDS
    removed = 0
    for entry in home().iterdir():
        name = entry.name
        suffix = next((s for s in _SESSION_FILE_SUFFIXES if name.endswith(s)), None)
        if suffix is None or not entry.is_file():
            continue
        session = name[: -len(suffix)]
        try:
            if entry.stat().st_mtime > cutoff or live_pid(session) is not None:
                continue
            if socket_path(session).exists():
                continue
            entry.unlink()
            removed += 1
        except (OSError, ValueError):
            continue
    return removed
