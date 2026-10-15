"""Shared fixtures. Every identifier is SYNTHETIC: generated per run from a
seeded RNG in the shape of the real type (Aadhaar with a valid Verhoeff
check digit, PAN shape, 6-9 mobile), never a real person's data."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from maskflow_agent import paths, protocol
from maskflow_pack_india.checksums import verhoeff_generate

_RNG = random.Random(20261014)
_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"


def synthetic_aadhaar() -> str:
    base = _RNG.choice("23456789") + "".join(_RNG.choice("0123456789") for _ in range(10))
    return base + verhoeff_generate(base)


def synthetic_pan() -> str:
    return (
        "".join(_RNG.choice(_LETTERS) for _ in range(3))
        + "P"
        + _RNG.choice(_LETTERS)
        + "".join(_RNG.choice("0123456789") for _ in range(4))
        + _RNG.choice(_LETTERS)
    )


def synthetic_mobile() -> str:
    return _RNG.choice("6789") + "".join(_RNG.choice("0123456789") for _ in range(9))


@pytest.fixture(scope="session")
def agent_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    home = tmp_path_factory.mktemp("agent-home")
    old = os.environ.get("MASKFLOW_AGENT_HOME")
    os.environ["MASKFLOW_AGENT_HOME"] = str(home)
    paths.home.cache_clear()
    paths._socket_dir.cache_clear()
    yield home
    if old is None:
        os.environ.pop("MASKFLOW_AGENT_HOME", None)
    else:
        os.environ["MASKFLOW_AGENT_HOME"] = old
    paths.home.cache_clear()
    paths._socket_dir.cache_clear()


def run_hook(event: str, payload: dict[str, Any], cwd: Path | None = None) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "maskflow_agent", "hook", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=cwd,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    out: dict[str, Any] = json.loads(proc.stdout) if proc.stdout.strip() else {}
    out["_raw"] = proc.stdout
    return out


@pytest.fixture(scope="session")
def session_id(agent_home: Path) -> Iterator[str]:
    """One live daemon (full engine, spaCy if installed) shared by the
    module's tests -- started through the real SessionStart hook."""
    sid = f"test-{uuid.uuid4().hex[:12]}"
    run_hook("session-start", {"session_id": sid, "hook_event_name": "SessionStart"})
    assert protocol.ping(sid)
    yield sid
    try:
        protocol.request(sid, "end", timeout=5)
    except protocol.DaemonUnavailable:
        pass


@pytest.fixture()
def fresh_session(agent_home: Path) -> Iterator[str]:
    sid = f"fresh-{uuid.uuid4().hex[:12]}"
    yield sid
    try:
        protocol.request(sid, "end", timeout=5)
    except protocol.DaemonUnavailable:
        pass


def run_agent_hook(
    agent: str, event: str, payload: Any, raw: str | None = None
) -> tuple[dict[str, Any], str, int]:
    """One adapter hook as the agent runs it: fresh process, JSON on stdin.
    Returns (parsed stdout or {}, raw stdout, exit code)."""
    proc = subprocess.run(
        [sys.executable, "-m", "maskflow_agent", "hook", "--agent", agent, event],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return out, proc.stdout, proc.returncode


def token_for(session_id: str, value: str) -> str:
    """The session's placeholder for a synthetic PAN."""
    masked = protocol.request(session_id, "mask_value", value=f"pan: {value}")["value"]
    start = masked.index("<PAN_")
    return str(masked[start : masked.index(">", start) + 1])
