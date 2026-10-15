"""Cursor (desktop agent and CLI). Hooks: `.cursor/hooks.json` (project) or
`~/.cursor/hooks.json` (user).

Cursor's hooks can rewrite a tool call before it runs (`preToolUse` ->
`updated_input`) but can replace a result afterwards only for MCP tools
(`postToolUse` -> `updated_mcp_tool_output`). So Cursor runs in wrap mode:

* `Shell` commands are rewritten into the mask-only wrapper; allowlisted
  commands with placeholders get the ticketed run-time restore;
* `Grep` is denied with a hint to search through the shell;
* `beforeReadFile` (the agent's reads and @-attached files) and
  `beforeTabFileRead` (Tab completion, which also sends file content to a
  model) are denied when the file holds personal data;
* MCP results are masked after the fact, the one result Cursor lets a hook
  replace.

Before-hooks are installed with `failClosed: true`, under which a crash, a
timeout, a non-zero exit *or an empty answer* blocks the action -- so every
before-hook here always answers explicitly.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

from .. import config, guard

EVENTS = (
    "sessionStart",
    "preToolUse",
    "postToolUse",
    "beforeReadFile",
    "beforeTabFileRead",
    "beforeSubmitPrompt",
    "sessionEnd",
)

_SHELL = {"Shell", "run_terminal_cmd"}
_WRITE = {"Write", "Edit", "Delete", "MultiEdit", "StrReplace", "edit_file", "search_replace"}
_SEARCH = {"Grep", "grep", "codebase_search", "SemanticSearch"}
_ALLOW: dict[str, Any] = {"permission": "allow"}


def _session(payload: dict[str, Any]) -> str:
    sid = payload.get("conversation_id") or payload.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    roots = payload.get("workspace_roots") or [""]
    import hashlib

    return "cursor-" + hashlib.sha256(str(roots[0]).encode("utf-8")).hexdigest()[:16]


def _kind(tool: str) -> str:
    if tool in _SHELL:
        return "shell"
    if tool in _WRITE:
        return "write"
    if tool in _SEARCH:
        return "search"
    return "other"  # Read is gated by beforeReadFile, MCP masked after the call


def _deny(reason: str) -> dict[str, Any]:
    return {"permission": "deny", "user_message": reason, "agent_message": reason}


def _pre_tool(sid: str, payload: dict[str, Any]) -> dict[str, Any]:
    tool = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            pass
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    pre = guard.pre_tool(
        sid,
        kind=_kind(tool),
        tool_input=tool_input,
        command=command if isinstance(command, str) else None,
        cwd=payload.get("cwd"),
        wrap_all=True,
    )
    if pre.deny is not None:
        return _deny(pre.deny)
    if pre.command is not None and isinstance(tool_input, dict):
        out: dict[str, Any] = {
            "permission": "allow",
            "updated_input": {**tool_input, "command": pre.command},
        }
        if pre.note is not None:
            out["agent_message"] = pre.note
        return out
    return dict(_ALLOW)


def _post_tool(sid: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not str(payload.get("tool_name", "")).startswith("MCP:"):
        return None  # Cursor can't replace a built-in tool's result
    raw = payload.get("tool_output")
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        value = raw
    masked = guard.mask_output(sid, value)
    if masked is None:
        return None
    if not isinstance(masked, dict):
        masked = {"content": [{"type": "text", "text": json.dumps(masked, ensure_ascii=False)}]}
    return {"updated_mcp_tool_output": masked}


def _read_gate(sid: str, payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("content")
    pre = guard.pre_tool(
        sid,
        kind="read",
        tool_input={},
        wrap_all=True,
        read_path=payload.get("file_path") if isinstance(payload.get("file_path"), str) else None,
        read_content=content if isinstance(content, str) else None,
    )
    if pre.deny is not None:
        return {"permission": "deny", "user_message": pre.deny}
    return dict(_ALLOW)


def handle(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    sid = _session(payload)
    if event == "sessionStart":
        ok = guard.ensure_daemon(sid)
        return {"additional_context": guard.CONTEXT if ok else guard.GUARD_DOWN}, 0
    if event == "preToolUse":
        return _pre_tool(sid, payload), 0
    if event == "postToolUse":
        return _post_tool(sid, payload), 0
    if event == "beforeReadFile":
        return _read_gate(sid, payload), 0
    if event == "beforeTabFileRead":
        return {"permission": _read_gate(sid, payload)["permission"]}, 0
    if event == "beforeSubmitPrompt":
        cfg = config.load(payload.get("cwd") or None)
        found = None
        if cfg.prompt_mode != "off":
            found = guard.prompt_findings(sid, str(payload.get("prompt", "")))
        if found is not None and cfg.prompt_mode == "block":
            return {"continue": False, "user_message": guard.prompt_blocked(found)}, 0
        if found is not None:
            return {"continue": True, "user_message": guard.prompt_warning(found)}, 0
        return {"continue": True}, 0
    if event == "sessionEnd":
        guard.end_session(sid)
    return None, 0


def fail(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    reason = "MaskFlow PII guard error. Ask the user to run `maskflow-agent doctor`."
    if event in ("preToolUse", "beforeReadFile"):
        return _deny(reason), 0
    if event == "beforeTabFileRead":
        return {"permission": "deny"}, 0
    if event == "postToolUse":  # ignored by Cursor for non-MCP tools
        return {
            "updated_mcp_tool_output": {"content": [{"type": "text", "text": guard.WITHHELD}]}
        }, 0
    if event == "beforeSubmitPrompt":
        return {"continue": True}, 0  # prompts are advisory
    return None, 0


# -- install ------------------------------------------------------------------------
_TIMEOUTS = {
    "sessionStart": 180,
    "preToolUse": 180,
    "postToolUse": 180,
    "beforeReadFile": 120,
    "beforeTabFileRead": 30,
    "beforeSubmitPrompt": 30,
    "sessionEnd": 5,
}
_FAIL_CLOSED = {"preToolUse", "beforeReadFile", "beforeTabFileRead"}
_MARKER = "--agent cursor"


def config_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".cursor" / "hooks.json"
    return cwd / ".cursor" / "hooks.json"


def _command(event: str, portable: bool) -> str:
    argv = ["hook", "--agent", "cursor", event]
    if portable:
        return shlex.join(["maskflow-agent", *argv])
    return shlex.join([sys.executable, "-m", "maskflow_agent", *argv])


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def _is_ours(entry: Any) -> bool:
    return isinstance(entry, dict) and _MARKER in str(entry.get("command", ""))


def _strip(data: dict[str, Any]) -> dict[str, Any]:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return data
    for event in list(hooks):
        entries = hooks[event]
        if isinstance(entries, list):
            kept = [e for e in entries if not _is_ours(e)]
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    return data


def install(path: Path, portable: bool = False) -> None:
    """Add our hooks to `path`, keeping every other hook in it."""
    data = _strip(_load(path))
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    for event in EVENTS:
        entry: dict[str, Any] = {"command": _command(event, portable), "timeout": _TIMEOUTS[event]}
        if event in _FAIL_CLOSED:
            entry["failClosed"] = True
        hooks.setdefault(event, []).append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def uninstall(path: Path) -> bool:
    if not is_installed(path):
        return False
    data = _strip(_load(path))
    if data.get("hooks") or set(data) - {"version", "hooks"}:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    else:
        path.unlink()
    return True


def is_installed(path: Path) -> bool:
    try:
        hooks = _load(path).get("hooks", {})
    except (OSError, ValueError):
        return False
    return any(
        _is_ours(e) for entries in hooks.values() if isinstance(entries, list) for e in entries
    )


def probe(session_id: str, text: str) -> tuple[str, dict[str, Any]]:
    return "postToolUse", {
        "conversation_id": session_id,
        "tool_name": "MCP:query",
        "tool_input": {},
        "tool_output": json.dumps({"content": [{"type": "text", "text": text}]}),
    }
