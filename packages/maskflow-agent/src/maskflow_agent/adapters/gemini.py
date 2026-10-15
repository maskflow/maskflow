"""Gemini CLI. Hooks live in `.gemini/settings.json` (project) or
`~/.gemini/settings.json` (user). Google replaced Gemini CLI with
Antigravity CLI on 2026-06-18 (see `antigravity.py`); this adapter is for
installs that still run it.

`AfterTool` can't hand back an edited result, but `decision: "deny"`
replaces the result sent to the model with the hook's `reason`. The guard
uses that channel to return the masked result for every tool: shell,
`read_file`, search, web and MCP. `BeforeTool` can rewrite a tool's
arguments (`hookSpecificOutput.tool_input`) without touching approvals, so
allowlisted commands get the ticketed run-time restore.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config, guard
from . import _files

EVENTS = ("SessionStart", "BeforeTool", "AfterTool", "BeforeAgent", "SessionEnd")

_SHELL = {"run_shell_command"}
_WRITE = {"write_file", "replace", "edit"}
_HEADER = "[maskflow: personal data in this output is replaced with placeholders]\n"


def _kind(tool: str) -> str:
    if tool in _SHELL:
        return "shell"
    if tool in _WRITE:
        return "write"
    return "other"


def _text(response: Any) -> Any:
    """The part of a tool response the model reads."""
    if isinstance(response, dict) and "llmContent" in response:
        return response["llmContent"]
    return response


def _shell_command(payload: dict[str, Any]) -> str | None:
    tool_input = payload.get("tool_input")
    if _kind(str(payload.get("tool_name", ""))) != "shell" or not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    return command if isinstance(command, str) else None


def handle(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    sid = str(payload.get("session_id") or "")
    if not sid:
        return fail(event, payload)
    if event == "SessionStart":
        ok = guard.ensure_daemon(sid, payload.get("transcript_path"))
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": guard.CONTEXT if ok else guard.GUARD_DOWN,
            }
        }, 0
    if event == "BeforeTool":
        tool_input = payload.get("tool_input") or {}
        command = _shell_command(payload)
        pre = guard.pre_tool(
            sid,
            kind=_kind(str(payload.get("tool_name", ""))),
            tool_input=tool_input,
            command=command,
            cwd=payload.get("cwd"),
            transcript_path=payload.get("transcript_path"),
        )
        if pre.deny is not None:
            return {"decision": "deny", "reason": pre.deny}, 0
        if pre.command is not None:
            return {"hookSpecificOutput": {"tool_input": {"command": pre.command}}}, 0
        if pre.note is not None:
            return {"systemMessage": pre.note}, 0
        return None, 0
    if event == "AfterTool":
        text = _text(payload.get("tool_response"))
        masked = guard.mask_output(sid, text, _shell_command(payload))
        if masked is None:
            return None, 0
        body = masked if isinstance(masked, str) else json.dumps(masked, ensure_ascii=False)
        return {"decision": "deny", "reason": body if guard.WITHHELD in body else _HEADER + body}, 0
    if event == "BeforeAgent":
        cfg = config.load(payload.get("cwd"))
        if cfg.prompt_mode == "off":
            return None, 0
        found = guard.prompt_findings(sid, str(payload.get("prompt", "")))
        if found is None:
            return None, 0
        if cfg.prompt_mode == "block":
            return {"decision": "deny", "reason": guard.prompt_blocked(found)}, 0
        return {"systemMessage": guard.prompt_warning(found)}, 0
    if event == "SessionEnd":
        guard.end_session(sid)
    return None, 0


def fail(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    if event == "AfterTool":
        return {"decision": "deny", "reason": guard.WITHHELD}, 0
    if event == "BeforeTool":
        return {
            "decision": "deny",
            "reason": "MaskFlow PII guard error. Ask the user to run `maskflow-agent doctor`.",
        }, 0
    return None, 0


# -- install ------------------------------------------------------------------------
_TIMEOUTS_MS = {
    "SessionStart": 180_000,
    "BeforeTool": 180_000,
    "AfterTool": 180_000,
    "BeforeAgent": 30_000,
    "SessionEnd": 3_000,
}


def config_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".gemini" / "settings.json"
    return cwd / ".gemini" / "settings.json"


def install(path: Path, portable: bool = False) -> None:
    data = _files.load(path)
    hooks = data.setdefault("hooks", {})
    _files.strip_groups(hooks, "gemini")
    for event in EVENTS:
        handler = {
            "type": "command",
            "name": "maskflow-agent",
            "command": _files.command("gemini", event, portable),
            "timeout": _TIMEOUTS_MS[event],
        }
        group: dict[str, Any] = {"hooks": [handler]}
        if event in ("BeforeTool", "AfterTool"):
            group = {"matcher": ".*", **group}
        hooks.setdefault(event, []).append(group)
    _files.write(path, data)


def uninstall(path: Path) -> bool:
    if not is_installed(path):
        return False
    data = _files.load(path)
    _files.strip_groups(data["hooks"], "gemini")
    if not data["hooks"]:
        del data["hooks"]
    if data:
        _files.write(path, data)
    else:
        path.unlink()
    return True


def is_installed(path: Path) -> bool:
    try:
        return _files.has_groups(_files.load(path).get("hooks"), "gemini")
    except (OSError, ValueError):
        return False


def probe(session_id: str, text: str) -> tuple[str, dict[str, Any]]:
    return "AfterTool", {
        "session_id": session_id,
        "hook_event_name": "AfterTool",
        "tool_name": "read_file",
        "tool_input": {"absolute_path": "/tmp/kyc.csv"},
        "tool_response": {"llmContent": text, "returnDisplay": "Read kyc.csv"},
    }
