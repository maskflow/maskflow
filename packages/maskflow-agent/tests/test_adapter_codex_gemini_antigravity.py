"""Codex CLI, Gemini CLI and Antigravity adapters, driven as each agent
drives them (fresh process, JSON on stdin). Payload shapes follow each
agent's hooks reference. Synthetic identifiers only."""

from __future__ import annotations

import json
import subprocess
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
from maskflow_agent.adapters import antigravity, codex, gemini

AADHAAR, PAN, MOBILE = synthetic_aadhaar(), synthetic_pan(), synthetic_mobile()
CSV = f"id,aadhaar,pan,mobile\n1,{AADHAAR},{PAN},{MOBILE}\n"
CANARIES = (AADHAAR, PAN, MOBILE)


def _clean(raw: str) -> bool:
    return not any(c in raw for c in CANARIES)


# -- Codex ----------------------------------------------------------------------------
def cx(event: str, session_id: str, **fields: Any) -> tuple[dict[str, Any], str, int]:
    payload = {"session_id": session_id, "hook_event_name": event, "cwd": "/tmp",
               "model": "m", "turn_id": "t1", "permission_mode": "default", **fields}  # fmt: skip
    return run_agent_hook("codex", event, payload)


@pytest.mark.leak
@pytest.mark.parametrize(
    ("tool", "response"),
    [
        ("Bash", CSV),
        ("exec_command", {"output": CSV, "exit_code": 0}),
        ("mcp__db__query", [{"type": "text", "text": CSV}]),
    ],
)
def test_codex_result_replaced_by_masked_reason(
    session_id: str, tool: str, response: object
) -> None:
    out, raw, code = cx(
        "PostToolUse", session_id, tool_name=tool, tool_use_id="u1",
        tool_input={"command": "cat k.csv"}, tool_response=response,
    )  # fmt: skip
    assert code == 0 and _clean(raw)
    assert out["decision"] == "block"
    assert "<AADHAAR_" in out["reason"] and out["reason"].startswith("[maskflow:")


def test_codex_exit_code_kept_in_rendered_result(session_id: str) -> None:
    out, _, _ = cx(
        "PostToolUse", session_id, tool_name="exec_command", tool_input={"cmd": "cat k"},
        tool_response={"output": f"pan {PAN}", "exit_code": 2},
    )  # fmt: skip
    assert out["reason"].endswith("[exit code 2]")


def test_codex_clean_result_untouched(session_id: str) -> None:
    _, raw, _ = cx("PostToolUse", session_id, tool_name="Bash", tool_input={}, tool_response="ok")
    assert raw == ""


@pytest.mark.leak
def test_codex_guard_down_withholds(agent_home: Path) -> None:
    out, raw, _ = cx(
        "PostToolUse", f"nobody-{uuid.uuid4().hex[:8]}", tool_name="Bash", tool_response=CSV
    )
    assert _clean(raw) and out == {"decision": "block", "reason": guard.WITHHELD}


@pytest.mark.leak
def test_codex_missing_session_fails_closed(agent_home: Path) -> None:
    out, raw, _ = run_agent_hook(
        "codex", "PostToolUse", {"tool_name": "Bash", "tool_response": CSV}
    )
    assert _clean(raw) and out["decision"] == "block"


def test_codex_restores_only_when_session_runs_without_asking(session_id: str) -> None:
    token = token_for(session_id, synthetic_pan())
    cmd = f"psql -c \"select 1 where pan='{token}'\""
    asking, _, _ = cx("PreToolUse", session_id, tool_name="Bash", tool_input={"command": cmd})
    spec = asking["hookSpecificOutput"]
    assert "updatedInput" not in spec and "permissionDecision" not in spec
    assert "passed literally" in spec["additionalContext"]

    auto, _, _ = cx(
        "PreToolUse", session_id, tool_name="Bash", tool_input={"command": cmd},
        permission_mode="bypassPermissions",
    )  # fmt: skip
    spec = auto["hookSpecificOutput"]
    assert spec["permissionDecision"] == "allow"
    assert "--ticket" in spec["updatedInput"]["command"]


def test_codex_list_command_and_cmd_key(session_id: str) -> None:
    token = token_for(session_id, synthetic_pan())
    out, _, _ = cx(
        "PreToolUse", session_id, tool_name="exec_command",
        tool_input={"cmd": ["psql", "-c", f"select '{token}'"]}, permission_mode="never",
    )  # fmt: skip
    assert "--ticket" in out["hookSpecificOutput"]["updatedInput"]["cmd"]


def test_codex_placeholder_patch_denied(session_id: str) -> None:
    token = token_for(session_id, synthetic_pan())
    out, _, _ = cx(
        "PreToolUse", session_id, tool_name="apply_patch",
        tool_input={"command": f"*** Begin Patch\n+pan={token}\n*** End Patch"},
    )  # fmt: skip
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_codex_prompt_warning(session_id: str) -> None:
    out, raw, _ = cx("UserPromptSubmit", session_id, prompt=f"fix {PAN}")
    assert PAN not in raw and "PAN x1" in out["systemMessage"]


def test_codex_install_merges(tmp_path: Path) -> None:
    path = codex.config_path("project", tmp_path)
    path.parent.mkdir()
    path.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command": "./x.sh"}]}]}}))
    codex.install(path)
    codex.install(path)
    data = json.loads(path.read_text())
    assert len(data["hooks"]["PostToolUse"]) == 1
    assert data["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] <= 3
    assert codex.is_installed(path) and codex.uninstall(path)
    assert json.loads(path.read_text()) == {"hooks": {"Stop": [{"hooks": [{"command": "./x.sh"}]}]}}


# -- Gemini CLI ------------------------------------------------------------------------
def gm(event: str, session_id: str, **fields: Any) -> tuple[dict[str, Any], str, int]:
    payload = {"session_id": session_id, "hook_event_name": event, "cwd": "/tmp", **fields}
    return run_agent_hook("gemini", event, payload)


@pytest.mark.leak
@pytest.mark.parametrize("tool", ["run_shell_command", "read_file", "mcp_db_query"])
def test_gemini_result_replaced_by_masked_reason(session_id: str, tool: str) -> None:
    out, raw, _ = gm(
        "AfterTool", session_id, tool_name=tool, tool_input={"command": "cat k.csv"},
        tool_response={"llmContent": CSV, "returnDisplay": "done"},
    )  # fmt: skip
    assert _clean(raw)
    assert out["decision"] == "deny" and "<AADHAAR_" in out["reason"]


@pytest.mark.leak
def test_gemini_guard_down_withholds(agent_home: Path) -> None:
    out, raw, _ = gm(
        "AfterTool", f"nobody-{uuid.uuid4().hex[:8]}", tool_name="read_file",
        tool_response={"llmContent": CSV},
    )  # fmt: skip
    assert _clean(raw) and out == {"decision": "deny", "reason": guard.WITHHELD}


def test_gemini_allowlisted_command_rewritten(session_id: str) -> None:
    token = token_for(session_id, synthetic_pan())
    out, _, _ = gm(
        "BeforeTool", session_id, tool_name="run_shell_command",
        tool_input={"command": f"sqlite3 db \"select '{token}'\""},
    )  # fmt: skip
    assert "--ticket" in out["hookSpecificOutput"]["tool_input"]["command"]


def test_gemini_placeholder_write_denied(session_id: str) -> None:
    token = token_for(session_id, synthetic_pan())
    out, _, _ = gm(
        "BeforeTool", session_id, tool_name="write_file",
        tool_input={"file_path": "a", "content": token},
    )  # fmt: skip
    assert out["decision"] == "deny"


def test_gemini_install_merges_settings(tmp_path: Path) -> None:
    path = gemini.config_path("project", tmp_path)
    path.parent.mkdir()
    path.write_text(json.dumps({"theme": "dark"}))
    gemini.install(path)
    data = json.loads(path.read_text())
    assert data["theme"] == "dark"
    assert data["hooks"]["AfterTool"][0]["matcher"] == ".*"
    assert data["hooks"]["AfterTool"][0]["hooks"][0]["timeout"] >= 120_000
    assert gemini.uninstall(path)
    assert json.loads(path.read_text()) == {"theme": "dark"}


# -- Antigravity (wrap mode) --------------------------------------------------------
def ag(session_id: str, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], str, int]:
    payload = {"conversationId": session_id, "workspacePaths": ["/tmp"], "stepIdx": 3,
               "toolCall": {"name": name, "args": args}}  # fmt: skip
    return run_agent_hook("antigravity", "PreToolUse", payload)


@pytest.mark.leak
def test_antigravity_command_wrapped_and_output_masked(session_id: str, tmp_path: Path) -> None:
    (tmp_path / "k.csv").write_text(CSV)
    out, _, _ = ag(session_id, "run_command", {"CommandLine": "cat k.csv", "Cwd": str(tmp_path)})
    assert out["decision"] == "allow"
    command = antigravity.rewritten(out)
    assert command == guard.mask_only_command(session_id, "cat k.csv")
    proc = subprocess.run(
        ["bash", "-c", command], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert _clean(proc.stdout) and "<AADHAAR_" in proc.stdout


@pytest.mark.parametrize(
    ("name", "args"),
    [("grep_search", {"Query": "x", "SearchPath": "/"}), ("mcp_db_query", {})],
)
def test_antigravity_search_and_mcp_denied(session_id: str, name: str, args: dict) -> None:
    out, _, _ = ag(session_id, name, args)
    assert out["decision"] == "deny"


@pytest.mark.leak
def test_antigravity_view_file_gate(session_id: str, tmp_path: Path) -> None:
    (tmp_path / "k.csv").write_text(CSV)
    (tmp_path / "a.py").write_text("x = 1\n")
    denied, raw, _ = ag(session_id, "view_file", {"AbsolutePath": str(tmp_path / "k.csv")})
    assert denied["decision"] == "deny" and _clean(raw)
    allowed, _, _ = ag(session_id, "view_file", {"AbsolutePath": str(tmp_path / "a.py")})
    assert allowed == {"decision": "allow"}


def test_antigravity_never_auto_approves(session_id: str) -> None:
    for name, args in (("run_command", {"CommandLine": "ls"}), ("list_dir", {"Path": "/"})):
        out, raw, _ = ag(session_id, name, args)
        assert "auto_approve" not in raw


def test_antigravity_missing_conversation_denies(agent_home: Path) -> None:
    out, _, _ = run_agent_hook(
        "antigravity", "PreToolUse", {"toolCall": {"name": "run_command", "args": {}}}
    )
    assert out["decision"] == "deny"


def test_antigravity_install_keeps_other_named_hooks(tmp_path: Path) -> None:
    path = antigravity.config_path("project", tmp_path)
    path.parent.mkdir()
    other = {"lint": {"PostToolUse": [{"matcher": "*", "hooks": [{"command": "./lint"}]}]}}
    path.write_text(json.dumps(other))
    antigravity.install(path)
    data = json.loads(path.read_text())
    assert data["lint"] == other["lint"]
    assert data["maskflow-agent"]["PreToolUse"][0]["matcher"] == "*"
    assert antigravity.is_installed(path) and antigravity.uninstall(path)
    assert json.loads(path.read_text()) == other


def test_support_status_is_measured() -> None:
    from maskflow_agent import adapters

    # Only agents that passed a live session test are "verified".
    assert adapters.STATUS["codex"] == "verified"
    assert {a for a, s in adapters.STATUS.items() if s == "verified"} == {"codex"}
