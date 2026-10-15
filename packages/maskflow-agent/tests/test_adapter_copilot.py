"""GitHub Copilot adapter, driven as Copilot drives it: a fresh process per
hook, JSON on stdin. Payload shapes follow GitHub's Copilot CLI hooks
reference (camelCase) and VS Code's Local-harness hooks reference
(snake_case). Synthetic identifiers only."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import synthetic_aadhaar, synthetic_mobile, synthetic_pan
from maskflow_agent import guard, protocol
from maskflow_agent.adapters import copilot

AADHAAR, PAN, MOBILE = synthetic_aadhaar(), synthetic_pan(), synthetic_mobile()
CSV = f"id,aadhaar,pan,mobile\n1,{AADHAAR},{PAN},{MOBILE}\n"
CANARIES = (AADHAAR, PAN, MOBILE)


def hook(event: str, payload: Any, raw: str | None = None) -> tuple[dict[str, Any], str, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "maskflow_agent", "hook", "--agent", "copilot", event],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return out, proc.stdout, proc.returncode


def _token_for(session_id: str, value: str) -> str:
    masked = protocol.request(session_id, "mask_value", value=f"pan: {value}")["value"]
    start = masked.index("<PAN_")
    return masked[start : masked.index(">", start) + 1]


# -- Copilot CLI / cloud agent (camelCase) ------------------------------------------
def test_cli_session_start_adds_context(session_id: str) -> None:
    out, _, code = hook("sessionStart", {"sessionId": session_id, "source": "new"})
    assert code == 0 and out["additionalContext"] == guard.CONTEXT


@pytest.mark.leak
@pytest.mark.parametrize("tool", ["bash", "view", "grep", "github-mcp-server-get_file"])
def test_cli_result_masked(session_id: str, tool: str) -> None:
    out, raw, code = hook(
        "postToolUse",
        {"sessionId": session_id, "toolName": tool, "toolArgs": {"command": "cat k.csv"},
         "toolResult": {"resultType": "success", "textResultForLlm": CSV}},
    )  # fmt: skip
    assert code == 0
    assert not any(c in raw for c in CANARIES)
    assert out["modifiedResult"]["resultType"] == "success"
    assert "<AADHAAR_" in out["modifiedResult"]["textResultForLlm"]


def test_cli_tool_args_as_json_string(session_id: str) -> None:
    mobile = synthetic_mobile()
    out, raw, _ = hook(
        "postToolUse",
        {"sessionId": session_id, "toolName": "bash",
         "toolArgs": json.dumps({"command": "sqlite3 db 'select name, mobile from k'"}),
         "toolResult": {"resultType": "success", "textResultForLlm": f"Ravi|{mobile}\n"}},
    )  # fmt: skip
    assert mobile not in raw
    assert "<INDIAN_MOBILE_" in out["modifiedResult"]["textResultForLlm"]


def test_cli_clean_result_untouched(session_id: str) -> None:
    out, raw, code = hook(
        "postToolUse",
        {"sessionId": session_id, "toolName": "bash", "toolArgs": {},
         "toolResult": {"resultType": "success", "textResultForLlm": "3 passed"}},
    )  # fmt: skip
    assert (out, raw, code) == ({}, "", 0)


@pytest.mark.leak
def test_cli_guard_down_withholds(agent_home: Path) -> None:
    out, raw, code = hook(
        "postToolUse",
        {"sessionId": f"nobody-{uuid.uuid4().hex[:8]}", "toolName": "bash",
         "toolResult": {"resultType": "success", "textResultForLlm": CSV}},
    )  # fmt: skip
    assert code == 0
    assert not any(c in raw for c in CANARIES)
    assert out["modifiedResult"]["textResultForLlm"] == guard.WITHHELD


@pytest.mark.leak
@pytest.mark.parametrize("event", ["postToolUse", "preToolUse"])
def test_cli_unreadable_payload_fails_closed(agent_home: Path, event: str) -> None:
    out, _, code = hook(event, None, raw="{not json")
    assert code == 0
    if event == "postToolUse":
        assert out["modifiedResult"]["textResultForLlm"] == guard.WITHHELD
    else:
        assert out["permissionDecision"] == "deny"


def test_cli_allowlisted_command_gets_ticketed_wrapper(session_id: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    args = {"command": f"sqlite3 db \"select '{token}'\"", "description": "q"}
    out, raw, _ = hook(
        "preToolUse", {"sessionId": session_id, "toolName": "bash", "toolArgs": args}
    )
    new = out["modifiedArgs"]
    assert new["description"] == "q"
    assert "--ticket" in new["command"] and token in new["command"]


def test_cli_plain_command_not_wrapped(session_id: str) -> None:
    out, raw, _ = hook(
        "preToolUse", {"sessionId": session_id, "toolName": "bash", "toolArgs": {"command": "ls"}}
    )
    assert raw == ""


@pytest.mark.parametrize("tool", ["create", "edit", "str_replace_editor", "apply_patch"])
def test_cli_placeholder_writes_denied(session_id: str, tool: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    out, _, _ = hook(
        "preToolUse",
        {"sessionId": session_id, "toolName": tool, "toolArgs": {"path": "a", "new_str": token}},
    )
    assert out["permissionDecision"] == "deny"


def test_cli_wrapper_invocation_denied(session_id: str) -> None:
    cmd = f"python -m maskflow_agent exec --session {session_id} --ticket x -- ls"
    out, _, _ = hook(
        "preToolUse", {"sessionId": session_id, "toolName": "bash", "toolArgs": {"command": cmd}}
    )
    assert out["permissionDecision"] == "deny"


# -- VS Code agent mode (snake_case, wrap mode) -------------------------------------
def _vs(event: str, session_id: str, **fields: Any) -> dict[str, Any]:
    return {"hook_event_name": event, "session_id": session_id, "cwd": "/tmp", **fields}


def test_vscode_shell_command_wrapped_mask_only(session_id: str) -> None:
    out, _, _ = hook(
        "preToolUse",
        _vs("PreToolUse", session_id, tool_name="run_in_terminal",
            tool_input={"command": "cat k.csv", "isBackground": False}),
    )  # fmt: skip
    spec = out["hookSpecificOutput"]
    assert spec["updatedInput"]["command"] == guard.mask_only_command(session_id, "cat k.csv")
    assert spec["updatedInput"]["isBackground"] is False
    assert "permissionDecision" not in spec  # VS Code's own approval flow still applies


@pytest.mark.parametrize("tool", ["grep_search", "semantic_search", "file_search"])
def test_vscode_search_denied(session_id: str, tool: str) -> None:
    out, _, _ = hook(
        "preToolUse", _vs("PreToolUse", session_id, tool_name=tool, tool_input={"query": "x"})
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_vscode_mcp_denied_with_proxy_hint(session_id: str) -> None:
    out, _, _ = hook(
        "preToolUse", _vs("PreToolUse", session_id, tool_name="mcp_db_query", tool_input={})
    )
    spec = out["hookSpecificOutput"]
    assert spec["permissionDecision"] == "deny"
    assert "maskflow-mcp" in spec["permissionDecisionReason"]


@pytest.mark.leak
def test_vscode_read_gate(session_id: str, tmp_path: Path) -> None:
    pii, clean = tmp_path / "k.csv", tmp_path / "notes.md"
    pii.write_text(CSV)
    clean.write_text("deploy on friday\n")
    denied, raw, _ = hook(
        "preToolUse",
        _vs("PreToolUse", session_id, tool_name="read_file", tool_input={"filePath": str(pii)}),
    )
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert not any(c in raw for c in CANARIES)
    allowed, raw, _ = hook(
        "preToolUse",
        _vs("PreToolUse", session_id, tool_name="read_file", tool_input={"filePath": str(clean)}),
    )
    assert raw == ""


def test_vscode_post_tool_use_is_a_no_op(session_id: str) -> None:
    _, raw, code = hook(
        "postToolUse",
        _vs("PostToolUse", session_id, tool_name="run_in_terminal", tool_input={},
            tool_response="masked already"),
    )  # fmt: skip
    assert (raw, code) == ("", 0)


def test_vscode_prompt_warning(session_id: str) -> None:
    out, raw, _ = hook(
        "userPromptSubmitted",
        _vs("UserPromptSubmit", session_id, prompt=f"fix the row for {PAN}"),
    )
    assert PAN not in raw
    assert "PAN x1" in out["systemMessage"]


def test_vscode_missing_session_id_falls_back_per_workspace() -> None:
    a = copilot._session({"hook_event_name": "PreToolUse", "cwd": "/w1"})
    assert a == copilot._session({"hook_event_name": "PostToolUse", "cwd": "/w1"})
    assert a != copilot._session({"hook_event_name": "PreToolUse", "cwd": "/w2"})


# -- install ------------------------------------------------------------------------------
def test_install_writes_one_file_for_cli_and_vscode(tmp_path: Path) -> None:
    path = copilot.config_path("project", tmp_path)
    assert path == tmp_path / ".github" / "hooks" / "maskflow-agent.json"
    copilot.install(path)
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert set(data["hooks"]) == set(copilot.EVENTS)
    entry = data["hooks"]["postToolUse"][0]
    assert entry["bash"] == entry["command"]
    assert "--agent copilot postToolUse" in entry["bash"]
    assert entry["timeoutSec"] >= 120
    assert copilot.is_installed(path)
    assert copilot.uninstall(path) and not path.exists()
    assert not copilot.uninstall(path)


def test_portable_install_uses_path_binary(tmp_path: Path) -> None:
    path = copilot.config_path("project", tmp_path)
    copilot.install(path, portable=True)
    entry = json.loads(path.read_text())["hooks"]["preToolUse"][0]
    assert entry["bash"].startswith("maskflow-agent hook --agent copilot")


def test_uninstall_leaves_foreign_file_alone(tmp_path: Path) -> None:
    path = copilot.config_path("project", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "hooks": {"preToolUse": [{"bash": "./lint.sh"}]}}))
    assert not copilot.uninstall(path)
    assert path.exists()


def test_cli_install_command(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "maskflow_agent", "install", "--agent", "copilot", "--portable"],
        cwd=tmp_path, capture_output=True, text=True, timeout=600, check=False,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr[-300:]
    assert "EXPERIMENTAL" in proc.stdout
    assert copilot.is_installed(copilot.config_path("project", tmp_path))
