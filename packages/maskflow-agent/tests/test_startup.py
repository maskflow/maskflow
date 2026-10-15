"""Daemon start-up under parallel hooks and slow (cold) engine loads: one
daemon per session, never two."""

from __future__ import annotations

import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import run_hook
from maskflow_agent import daemon, guard, install, paths, protocol


def _daemons_for(session_id: str) -> int:
    out = subprocess.run(
        ["pgrep", "-f", f"maskflow_agent daemon --session {session_id}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return len(out.split())


def test_parallel_hooks_start_exactly_one_daemon(fresh_session: str) -> None:
    payload = {"session_id": fresh_session, "tool_name": "Read", "tool_input": {"file_path": "x"}}
    with ThreadPoolExecutor(6) as pool:
        outs = list(pool.map(lambda _: run_hook("pre-tool-use", payload), range(6)))
    assert all(o == {"_raw": ""} for o in outs)  # every call allowed through
    assert protocol.ping(fresh_session)
    assert _daemons_for(fresh_session) == 1


def test_still_loading_daemon_is_waited_for_not_duplicated(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = f"loading-{uuid.uuid4().hex[:8]}"
    loading = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        paths.pid_path(session).write_text(str(loading.pid))  # alive, no socket yet
        spawned: list[str] = []
        monkeypatch.setattr(guard, "_spawn", spawned.append)
        monkeypatch.setattr(guard, "_START_TIMEOUT", 1.5)
        assert guard.ensure_daemon(session) is False
        assert spawned == []
    finally:
        loading.kill()
        paths.pid_path(session).unlink(missing_ok=True)


def test_dead_pid_file_does_not_block_a_start(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = f"stale-{uuid.uuid4().hex[:8]}"
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    paths.pid_path(session).write_text(str(dead.pid))
    spawned: list[str] = []
    monkeypatch.setattr(guard, "_spawn", spawned.append)
    monkeypatch.setattr(guard, "_START_TIMEOUT", 0.5)
    guard.ensure_daemon(session)
    assert spawned == [session]


def test_daemon_steps_aside_when_another_owns_the_session(agent_home: Path) -> None:
    session = f"owned-{uuid.uuid4().hex[:8]}"
    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        paths.pid_path(session).write_text(str(owner.pid))
        assert daemon.serve(session, idle_seconds=5, patterns_only=True) == 0
        assert not paths.socket_path(session).exists()
    finally:
        owner.kill()
        paths.pid_path(session).unlink(missing_ok=True)


def test_install_warm_up_loads_the_engine() -> None:
    ok, seconds = install.warm_up()
    assert ok
    assert seconds < 600
