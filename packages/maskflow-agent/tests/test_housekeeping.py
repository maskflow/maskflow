"""Per-session files don't pile up in MASKFLOW_AGENT_HOME."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from conftest import run_hook
from maskflow_agent import paths, protocol


def _wait_gone(session_id: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not paths.pid_path(session_id).exists() and not paths.log_path(session_id).exists():
            return
        time.sleep(0.2)


def test_clean_session_leaves_only_its_summary(fresh_session: str) -> None:
    run_hook("session-start", {"session_id": fresh_session})
    run_hook("post-tool-use", {"session_id": fresh_session, "tool_name": "Bash",
                               "tool_response": {"stdout": "ok"}})  # fmt: skip
    run_hook("session-end", {"session_id": fresh_session})
    _wait_gone(fresh_session)
    assert not protocol.ping(fresh_session)
    for leftover in (
        paths.start_lock_path(fresh_session),
        paths.log_path(fresh_session),
        paths.pid_path(fresh_session),
        paths.socket_path(fresh_session),
    ):
        assert not leftover.exists(), leftover.name
    assert paths.summary_path(fresh_session).exists()


def test_log_with_problems_is_kept(agent_home: Path) -> None:
    session = f"kept-{uuid.uuid4().hex[:8]}"
    paths.log_path(session).write_text("WARNING something worth reading\n")
    paths.start_lock_path(session).write_text("")
    paths.remove_session_files(session, keep_log=True)
    assert paths.log_path(session).exists()
    assert not paths.start_lock_path(session).exists()
    paths.remove_session_files(session, keep_log=False)
    assert not paths.log_path(session).exists()


def _age(path: Path, days: float) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_sweep_removes_only_old_files_of_dead_sessions(agent_home: Path) -> None:
    dead, recent, live = (f"{k}-{uuid.uuid4().hex[:8]}" for k in ("dead", "recent", "live"))
    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        for session in (dead, recent, live):
            for path in (paths.start_lock_path(session), paths.log_path(session)):
                path.write_text("")
        paths.pid_path(live).write_text(str(owner.pid))
        for session in (dead, live):
            for path in (paths.start_lock_path(session), paths.log_path(session)):
                _age(path, 8)
        _age(paths.pid_path(live), 8)

        assert paths.sweep_stale() >= 2
        assert not paths.start_lock_path(dead).exists()
        assert not paths.log_path(dead).exists()
        assert paths.start_lock_path(recent).exists()  # too new
        assert paths.log_path(live).exists()  # daemon still alive
        assert paths.pid_path(live).exists()
    finally:
        owner.kill()
        for session in (recent, live):
            for path in (paths.start_lock_path(session), paths.log_path(session),
                         paths.pid_path(session)):  # fmt: skip
                path.unlink(missing_ok=True)


def test_sweep_ignores_unrelated_files(agent_home: Path) -> None:
    keep = agent_home / "config.json"
    keep.write_text("{}")
    _age(keep, 30)
    paths.sweep_stale()
    assert keep.exists()
    keep.unlink()
