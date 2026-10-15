"""OpenAI Codex CLI. Hooks: `.codex/hooks.json` (project; loads only when
the project's `.codex/` layer is trusted) or `~/.codex/hooks.json`. Codex
runs a non-managed hook only after the user has reviewed it with `/hooks`.

Codex's `PostToolUse` can't hand back an edited result, but
`decision: "block"` *replaces* the tool result with the hook's `reason`.
The guard uses that channel to return the masked result, which gives Codex
the same after-the-fact masking as Claude Code. This covers shell,
`exec_command`, `apply_patch`, MCP and Codex's other local tools; Codex
has no built-in file reader, since it reads files through the shell.

Placeholders are restored at run time only when the session already runs
commands without asking: rewriting a command (`updatedInput`) requires
`permissionDecision: "allow"`, which would otherwise skip an approval the
user asked for. In an approval-requiring session they are passed literally,
with a note.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from .. import config, guard
from . import _files

EVENTS = ("SessionStart", "PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionEnd")

_SHELL = {"Bash", "shell", "local_shell", "exec_command", "unified_exec"}
_WRITE = {"apply_patch", "Edit", "Write"}
# Permission modes in which Codex already runs commands without asking, so
# auto-allowing a rewritten command grants nothing new.
_NO_PROMPT_MODES = {"bypassPermissions", "dontAsk", "never", "full-auto", "danger-full-access"}
_HEADER = "[maskflow: personal data in this output is replaced with placeholders]\n"


def _command(tool_input: Any) -> tuple[str | None, str | None]:
    """(key, command string) of a shell tool's input."""
    if not isinstance(tool_input, dict):
        return None, None
    for key in ("command", "cmd"):
        value = tool_input.get(key)
        if isinstance(value, str):
            return key, value
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            return key, shlex.join(value)
    return None, None


def _kind(tool: str) -> str:
    if tool in _SHELL:
        return "shell"
    if tool in _WRITE:
        return "write"
    return "other"


def _render(value: Any) -> str:
    """A masked tool result as the text the model gets in place of it."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = [str(value[k]) for k in ("output", "stdout", "aggregated_output") if value.get(k)]
        if value.get("stderr"):
            parts.append(f"[stderr]\n{value['stderr']}")
        code = value.get("exit_code", value.get("exitCode"))
        if parts:
            return "\n".join(parts) + (f"\n[exit code {code}]" if code is not None else "")
    return json.dumps(value, ensure_ascii=False)


def _pre(sid: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    tool = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    key, command = _command(tool_input) if _kind(tool) == "shell" else (None, None)
    no_prompt = payload.get("permission_mode") in _NO_PROMPT_MODES
    pre = guard.pre_tool(
        sid,
        kind=_kind(tool),
        tool_input=tool_input,
        command=command,
        cwd=payload.get("cwd"),
        transcript_path=payload.get("transcript_path"),
        user_rule=(lambda _c: "allow") if no_prompt else (lambda _c: None),
    )
    spec: dict[str, Any] = {"hookEventName": "PreToolUse"}
    if pre.deny is not None:
        spec.update(permissionDecision="deny", permissionDecisionReason=pre.deny)
        return {"hookSpecificOutput": spec}
    if pre.command is not None and key is not None:
        if pre.permission != "allow":
            spec["additionalContext"] = (
                "MaskFlow: this Codex session asks before running commands, so "
                "placeholders are not restored to real values here; they were passed "
                "literally."
            )
            return {"hookSpecificOutput": spec}
        spec.update(
            permissionDecision="allow",
            permissionDecisionReason="maskflow: placeholders are restored when this runs",
            updatedInput={**tool_input, key: pre.command},
        )
        return {"hookSpecificOutput": spec}
    if pre.note is not None:
        spec["additionalContext"] = pre.note
        return {"hookSpecificOutput": spec}
    return None


def _post(sid: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    response = payload.get("tool_response")
    tool_input = payload.get("tool_input") or {}
    _, command = (
        _command(tool_input)
        if _kind(str(payload.get("tool_name"))) == "shell"
        else (
            None,
            None,
        )
    )
    masked = guard.mask_output(sid, response, command)
    if masked is None:
        return None
    body = _render(masked)
    return {"decision": "block", "reason": body if guard.WITHHELD in body else _HEADER + body}


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
    if event == "PreToolUse":
        return _pre(sid, payload), 0
    if event == "PostToolUse":
        return _post(sid, payload), 0
    if event == "UserPromptSubmit":
        cfg = config.load(payload.get("cwd"))
        if cfg.prompt_mode == "off":
            return None, 0
        found = guard.prompt_findings(sid, str(payload.get("prompt", "")))
        if found is None:
            return None, 0
        if cfg.prompt_mode == "block":
            return {"decision": "block", "reason": guard.prompt_blocked(found)}, 0
        return {"systemMessage": guard.prompt_warning(found)}, 0
    if event == "SessionEnd":
        guard.end_session(sid)
    return None, 0


def fail(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    reason = "MaskFlow PII guard error. Ask the user to run `maskflow-agent doctor`."
    if event == "PostToolUse":
        return {"decision": "block", "reason": guard.WITHHELD}, 0
    if event == "PreToolUse":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }, 0
    return None, 0


# -- install ------------------------------------------------------------------------
_TIMEOUTS = {
    "SessionStart": 180,
    "PreToolUse": 180,
    "PostToolUse": 180,
    "UserPromptSubmit": 30,
    "SessionEnd": 3,
}


def config_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".codex" / "hooks.json"
    return cwd / ".codex" / "hooks.json"


def install(path: Path, portable: bool = False) -> None:
    data = _files.load(path)
    hooks = data.setdefault("hooks", {})
    _files.strip_groups(hooks, "codex")
    for event in EVENTS:
        handler = {
            "type": "command",
            "command": _files.command("codex", event, portable),
            "timeout": _TIMEOUTS[event],
        }
        hooks.setdefault(event, []).append({"hooks": [handler]})
    _files.write(path, data)


def uninstall(path: Path) -> bool:
    if not is_installed(path):
        return False
    data = _files.load(path)
    _files.strip_groups(data["hooks"], "codex")
    if not data["hooks"]:
        del data["hooks"]
    if data:
        _files.write(path, data)
    else:
        path.unlink()
    return True


def is_installed(path: Path) -> bool:
    try:
        return _files.has_groups(_files.load(path).get("hooks"), "codex")
    except (OSError, ValueError):
        return False


def probe(session_id: str, text: str) -> tuple[str, dict[str, Any]]:
    return "PostToolUse", {
        "session_id": session_id,
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "cat kyc.csv"},
        "tool_response": text,
    }


INSTALL_NOTE = (
    "Codex runs a hook only after you review it: start `codex`, run /hooks, and "
    "trust the maskflow-agent hooks. Project hooks also need the project trusted."
)
