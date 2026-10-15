"""Devin Desktop (Windsurf/Cascade) gate adapter. Cascade hooks can only
block (exit 2, stderr to the agent), and anything else lets the action
through -- so every refusal and every failure must exit 2. Synthetic
identifiers only."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import synthetic_aadhaar, synthetic_mobile, synthetic_pan, token_for
from maskflow_agent import guard
from maskflow_agent.adapters import devin

AADHAAR, PAN, MOBILE = synthetic_aadhaar(), synthetic_pan(), synthetic_mobile()
CSV = f"id,aadhaar,pan,mobile\n1,{AADHAAR},{PAN},{MOBILE}\n"
CANARIES = (AADHAAR, PAN, MOBILE)


def gate(
    event: str, session_id: str | None, raw: str | None = None, **info: Any
) -> tuple[str, int]:
    payload: dict[str, Any] = {"agent_action_name": event, "execution_id": "e1",
                               "tool_info": info}  # fmt: skip
    if session_id is not None:
        payload["trajectory_id"] = session_id
    proc = subprocess.run(
        [sys.executable, "-m", "maskflow_agent", "hook", "--agent", "devin", event],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert proc.stdout == ""
    return proc.stderr, proc.returncode


@pytest.mark.leak
def test_unwrapped_command_blocked_with_exact_replacement(session_id: str, tmp_path: Path) -> None:
    (tmp_path / "k.csv").write_text(CSV)
    stderr, code = gate("pre_run_command", session_id, command_line="cat k.csv", cwd=str(tmp_path))
    assert code == 2
    suggested = devin.rewritten(None, stderr)
    assert suggested == guard.mask_only_command(session_id, "cat k.csv")
    # the agent re-runs the suggestion: it passes the gate, and its output is masked
    assert gate("pre_run_command", session_id, command_line=suggested) == ("", 0)
    proc = subprocess.run(
        ["bash", "-c", suggested], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert not any(c in proc.stdout for c in CANARIES) and "<AADHAAR_" in proc.stdout


def test_wrapper_with_ride_along_still_blocked(session_id: str) -> None:
    cmd = guard.mask_only_command(session_id, "ls") + "; cat secrets.csv"
    _, code = gate("pre_run_command", session_id, command_line=cmd)
    assert code == 2


def test_wrapper_for_another_conversation_blocked(session_id: str) -> None:
    _, code = gate("pre_run_command", session_id, command_line=guard.mask_only_command("x", "ls"))
    assert code == 2


@pytest.mark.leak
def test_pii_file_read_blocked_with_wrapped_cat(session_id: str, tmp_path: Path) -> None:
    pii, clean = tmp_path / "k.csv", tmp_path / "a.py"
    pii.write_text(CSV)
    clean.write_text("x = 1\n")
    stderr, code = gate("pre_read_code", session_id, file_path=str(pii))
    assert code == 2 and not any(c in stderr for c in CANARIES)
    assert devin.rewritten(None, stderr) == guard.mask_only_command(session_id, f"cat {pii}")
    assert gate("pre_read_code", session_id, file_path=str(clean)) == ("", 0)
    assert gate("pre_read_code", session_id, file_path=str(tmp_path)) == ("", 0)


def test_mcp_blocked(session_id: str) -> None:
    stderr, code = gate("pre_mcp_tool_use", session_id, mcp_server_name="db", mcp_tool_name="q")
    assert code == 2 and "maskflow-mcp" in stderr


def test_placeholder_write_blocked(session_id: str) -> None:
    token = token_for(session_id, synthetic_pan())
    edits = [{"old_string": "x", "new_string": token}]
    _, code = gate("pre_write_code", session_id, file_path="a.csv", edits=edits)
    assert code == 2
    assert gate("pre_write_code", session_id, file_path="a.py", edits=[{"new_string": "y"}]) == (
        "",
        0,
    )


@pytest.mark.parametrize("event", ["pre_run_command", "pre_read_code", "pre_mcp_tool_use"])
def test_failures_exit_2(agent_home: Path, event: str) -> None:
    assert gate(event, None, raw="{broken")[1] == 2
    assert gate(event, None, command_line="ls", file_path="/x")[1] == 2  # no conversation id


def test_prompt_warn_mode_never_blocks(session_id: str) -> None:
    assert gate("pre_user_prompt", session_id, user_prompt=f"fix {PAN}") == ("", 0)


def test_prompt_block_mode(session_id: str, tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "maskflow-agent.json").write_text(json.dumps({"prompt_mode": "block"}))
    stderr, code = gate("pre_user_prompt", session_id, user_prompt=f"fix {PAN}", cwd=str(tmp_path))
    assert code == 2 and PAN not in stderr


def test_install_merges_and_uninstall_restores(tmp_path: Path) -> None:
    path = devin.config_path("project", tmp_path)
    path.parent.mkdir()
    mine = {"hooks": {"post_write_code": [{"command": "./fmt.sh", "show_output": True}]}}
    path.write_text(json.dumps(mine))
    devin.install(path)
    devin.install(path)
    data = json.loads(path.read_text())
    assert len(data["hooks"]["pre_run_command"]) == 1
    assert data["hooks"]["post_write_code"] == mine["hooks"]["post_write_code"]
    assert devin.is_installed(path) and devin.uninstall(path)
    assert json.loads(path.read_text()) == mine


def test_fresh_session_gate_starts_daemon(fresh_session: str) -> None:
    _, code = gate("pre_run_command", fresh_session, command_line="ls")
    assert code == 2  # started the daemon, then asked for the wrapped form
    assert gate("pre_run_command", f"x-{uuid.uuid4().hex[:6]}", raw="[]")[1] == 2
