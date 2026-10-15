"""Cursor adapter, driven as Cursor drives it (fresh process, JSON on
stdin). Payload shapes follow cursor.com/docs/agent/hooks. Synthetic
identifiers only."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import (
    run_agent_hook,
    synthetic_aadhaar,
    synthetic_mobile,
    synthetic_pan,
    token_for,
)
from maskflow_agent import guard
from maskflow_agent.adapters import cursor

AADHAAR, PAN, MOBILE = synthetic_aadhaar(), synthetic_pan(), synthetic_mobile()
CSV = f"id,aadhaar,pan,mobile\n1,{AADHAAR},{PAN},{MOBILE}\n"
CANARIES = (AADHAAR, PAN, MOBILE)


def hook(event: str, session_id: str, **fields: Any) -> tuple[dict[str, Any], str, int]:
    payload = {"conversation_id": session_id, "generation_id": "g1", "hook_event_name": event,
               "workspace_roots": ["/tmp/ws"], **fields}  # fmt: skip
    return run_agent_hook("cursor", event, payload)


def test_session_start_adds_context(session_id: str) -> None:
    out, _, _ = hook("sessionStart", session_id, is_background_agent=False)
    assert out["additional_context"] == guard.CONTEXT


def test_shell_wrapped_mask_only(session_id: str) -> None:
    out, _, _ = hook(
        "preToolUse", session_id, tool_name="Shell",
        tool_input={"command": "cat k.csv", "cwd": "/tmp/ws"}, cwd="/tmp/ws",
    )  # fmt: skip
    assert out["permission"] == "allow"
    assert out["updated_input"]["command"] == guard.mask_only_command(session_id, "cat k.csv")
    assert out["updated_input"]["cwd"] == "/tmp/ws"


def test_allowlisted_placeholder_command_gets_ticket(session_id: str) -> None:
    token = token_for(session_id, synthetic_pan())
    cmd = f"psql -c \"select 1 where pan='{token}'\""
    out, _, _ = hook("preToolUse", session_id, tool_name="Shell", tool_input={"command": cmd})
    assert "--ticket" in out["updated_input"]["command"]


def test_other_tools_answer_allow_explicitly(session_id: str) -> None:
    # failClosed treats an empty answer as a failure, so allow is explicit.
    out, raw, _ = hook("preToolUse", session_id, tool_name="Read", tool_input={"path": "x"})
    assert out == {"permission": "allow"}


@pytest.mark.parametrize("tool", ["Grep", "codebase_search"])
def test_search_denied(session_id: str, tool: str) -> None:
    out, _, _ = hook("preToolUse", session_id, tool_name=tool, tool_input={"pattern": "x"})
    assert out["permission"] == "deny"
    assert "rg" in out["agent_message"]


def test_placeholder_write_denied(session_id: str) -> None:
    token = token_for(session_id, synthetic_pan())
    out, _, _ = hook(
        "preToolUse", session_id, tool_name="Write", tool_input={"path": "a", "contents": token}
    )
    assert out["permission"] == "deny"


@pytest.mark.leak
@pytest.mark.parametrize("event", ["beforeReadFile", "beforeTabFileRead"])
def test_read_gates(session_id: str, event: str) -> None:
    denied, raw, _ = hook(event, session_id, file_path="/tmp/ws/k.csv", content=CSV)
    assert denied["permission"] == "deny"
    assert not any(c in raw for c in CANARIES)
    allowed, _, _ = hook(event, session_id, file_path="/tmp/ws/a.py", content="print('hi')\n")
    assert allowed == {"permission": "allow"}


@pytest.mark.leak
def test_mcp_output_masked(session_id: str) -> None:
    output = json.dumps({"content": [{"type": "text", "text": CSV}]})
    out, raw, _ = hook(
        "postToolUse", session_id, tool_name="MCP:query", tool_input={}, tool_output=output
    )
    assert not any(c in raw for c in CANARIES)
    text = out["updated_mcp_tool_output"]["content"][0]["text"]
    assert "<AADHAAR_" in text


def test_builtin_post_tool_use_is_a_no_op(session_id: str) -> None:
    _, raw, code = hook("postToolUse", session_id, tool_name="Shell", tool_output='"masked"')
    assert (raw, code) == ("", 0)


@pytest.mark.leak
def test_mcp_guard_down_withholds(agent_home: Path) -> None:
    output = json.dumps({"content": [{"type": "text", "text": CSV}]})
    out, raw, _ = hook(
        "postToolUse", f"nobody-{uuid.uuid4().hex[:8]}", tool_name="MCP:q", tool_output=output
    )
    assert not any(c in raw for c in CANARIES)
    assert out["updated_mcp_tool_output"]["content"][0]["text"] == guard.WITHHELD


@pytest.mark.leak
@pytest.mark.parametrize(
    ("event", "key", "value"),
    [("preToolUse", "permission", "deny"), ("beforeReadFile", "permission", "deny"),
     ("beforeTabFileRead", "permission", "deny")],
)  # fmt: skip
def test_unreadable_payload_fails_closed(
    agent_home: Path, event: str, key: str, value: str
) -> None:
    out, _, code = run_agent_hook("cursor", event, None, raw="{oops")
    assert code == 0 and out[key] == value


def test_prompt_warns_without_blocking(session_id: str) -> None:
    out, raw, _ = hook("beforeSubmitPrompt", session_id, prompt=f"row for {PAN}", attachments=[])
    assert out["continue"] is True
    assert PAN not in raw and "PAN x1" in out["user_message"]


def test_clean_prompt_continues(session_id: str) -> None:
    out, _, _ = hook("beforeSubmitPrompt", session_id, prompt="fix the build", attachments=[])
    assert out == {"continue": True}


# -- install ------------------------------------------------------------------------
def test_install_merges_and_uninstall_keeps_foreign_hooks(tmp_path: Path) -> None:
    path = cursor.config_path("project", tmp_path)
    path.parent.mkdir()
    path.write_text(json.dumps({"version": 1, "hooks": {"afterFileEdit": [{"command": "./f.sh"}]}}))
    cursor.install(path)
    cursor.install(path)  # idempotent
    data = json.loads(path.read_text())
    assert data["hooks"]["afterFileEdit"] == [{"command": "./f.sh"}]
    pre = data["hooks"]["preToolUse"]
    assert len(pre) == 1 and pre[0]["failClosed"] is True
    assert "failClosed" not in data["hooks"]["postToolUse"][0]
    assert cursor.is_installed(path)
    assert cursor.uninstall(path)
    assert json.loads(path.read_text()) == {
        "version": 1,
        "hooks": {"afterFileEdit": [{"command": "./f.sh"}]},
    }
    assert not cursor.uninstall(path)


def test_uninstall_removes_file_it_created(tmp_path: Path) -> None:
    path = cursor.config_path("project", tmp_path)
    cursor.install(path, portable=True)
    assert json.loads(path.read_text())["hooks"]["preToolUse"][0]["command"].startswith(
        "maskflow-agent hook --agent cursor"
    )
    assert cursor.uninstall(path) and not path.exists()
