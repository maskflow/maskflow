"""GitHub Copilot: Copilot CLI, the Copilot cloud agent, and VS Code agent
mode. All three read the same hook files (`.github/hooks/*.json`,
`~/.copilot/hooks/*.json`), so one installed file serves all of them, and
the payload says which harness is calling:

* Copilot CLI / cloud agent send camelCase payloads (`toolName`,
  `toolArgs`, `toolResult`). Their `postToolUse` can replace a tool's result
  (`modifiedResult`), so output is masked after the tool ran, as in Claude
  Code. Caveat: Copilot lets the original through when a hook times out or
  exits non-zero, so this module never exits non-zero on an after-tool
  event, and installs with a generous timeout.
* VS Code agent mode maps the same file to its own snake_case payloads
  (`hook_event_name`, `tool_name`, `tool_input`, `tool_response`). Its
  `PostToolUse` cannot replace a result, so VS Code runs in wrap mode:
  shell commands go through the mask-only wrapper, built-in search, MCP
  tools and PII-holding reads are denied with a hint.
"""

from __future__ import annotations

import hashlib
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
    "userPromptSubmitted",
    "sessionEnd",
)

# Copilot CLI tool names.
_CLI_SHELL = {"bash"}
_CLI_WRITE = {"create", "edit", "str_replace_editor", "apply_patch", "write"}

# VS Code Local-harness tool names (and Claude-style names, which VS Code
# can also report).
_VS_SHELL = {"run_in_terminal", "Bash"}
_VS_WRITE = {
    "create_file",
    "replace_string_in_file",
    "multi_replace_string_in_file",
    "insert_edit_into_file",
    "edit_notebook_file",
    "edit_file",
    "apply_patch",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
}
_VS_READ = {"read_file", "Read"}
_VS_SEARCH = {
    "grep_search",
    "file_search",
    "semantic_search",
    "list_code_usages",
    "search_workspace_symbols",
    "get_search_view_results",
    "find_text_in_files",
    "Grep",
}

MCP_DENIED = (
    "MaskFlow PII guard: this agent's hooks can't mask MCP tool results. Route "
    "this MCP server through the `maskflow-mcp` proxy so its results are masked, "
    "or ask the user to allow it."
)


def _is_vscode(payload: dict[str, Any]) -> bool:
    return "hook_event_name" in payload or "tool_name" in payload


def _session(payload: dict[str, Any]) -> str:
    sid = payload.get("sessionId") or payload.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    # VS Code documents the session id as optional: fall back to one mapping
    # per workspace, so placeholders stay consistent inside it.
    cwd = str(payload.get("cwd") or "")
    return "copilot-" + hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16]


def _args(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value if value is not None else {}


# -- Copilot CLI / cloud agent ----------------------------------------------------
def _cli_kind(tool: str) -> str:
    if tool in _CLI_SHELL:
        return "shell"
    if tool in _CLI_WRITE:
        return "write"
    return "other"


def _cli(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    sid = _session(payload)
    if event == "sessionStart":
        ok = guard.ensure_daemon(sid)
        return {"additionalContext": guard.CONTEXT if ok else guard.GUARD_DOWN}, 0
    if event == "preToolUse":
        tool = str(payload.get("toolName", ""))
        args = _args(payload.get("toolArgs"))
        command = args.get("command") if isinstance(args, dict) else None
        pre = guard.pre_tool(
            sid,
            kind=_cli_kind(tool),
            tool_input=args,
            command=command if isinstance(command, str) else None,
            cwd=payload.get("cwd"),
        )
        if pre.deny is not None:
            return {"permissionDecision": "deny", "permissionDecisionReason": pre.deny}, 0
        if pre.command is not None and isinstance(args, dict):
            return {"modifiedArgs": {**args, "command": pre.command}}, 0
        return None, 0
    if event == "postToolUse":
        result = payload.get("toolResult")
        text = result.get("textResultForLlm") if isinstance(result, dict) else None
        if not isinstance(text, str):
            return None, 0
        args = _args(payload.get("toolArgs"))
        command = args.get("command") if isinstance(args, dict) else None
        masked = guard.mask_output(
            sid,
            text,
            command if payload.get("toolName") in _CLI_SHELL and isinstance(command, str) else None,
        )
        if masked is None:
            return None, 0
        return {"modifiedResult": {"resultType": "success", "textResultForLlm": masked}}, 0
    if event == "sessionEnd":
        guard.end_session(sid)
    # userPromptSubmitted: Copilot drops a config hook's output for this
    # event, so there is no way to warn or block here.
    return None, 0


# -- VS Code agent mode (wrap mode) -----------------------------------------------
def _vs_kind(tool: str) -> str:
    if tool in _VS_SHELL:
        return "shell"
    if tool in _VS_WRITE:
        return "write"
    if tool in _VS_READ:
        return "read"
    if tool in _VS_SEARCH:
        return "search"
    if tool.startswith(("mcp_", "mcp__")):
        return "mcp"
    return "other"


def _vs_deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _read_path(tool_input: Any) -> str | None:
    if isinstance(tool_input, dict):
        for key in ("filePath", "file_path", "path"):
            if isinstance(tool_input.get(key), str):
                return str(tool_input[key])
    return None


def _vscode(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    sid = _session(payload)
    name = payload.get("hook_event_name") or event
    if name in ("SessionStart", "sessionStart"):
        ok = guard.ensure_daemon(sid, payload.get("transcript_path"))
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": guard.CONTEXT if ok else guard.GUARD_DOWN,
            }
        }, 0
    if name in ("PreToolUse", "preToolUse"):
        tool = str(payload.get("tool_name", ""))
        tool_input = _args(payload.get("tool_input"))
        kind = _vs_kind(tool)
        if kind == "mcp":
            return _vs_deny(MCP_DENIED), 0
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        pre = guard.pre_tool(
            sid,
            kind=kind,
            tool_input=tool_input,
            command=command if isinstance(command, str) else None,
            cwd=payload.get("cwd"),
            transcript_path=payload.get("transcript_path"),
            wrap_all=True,
            read_path=_read_path(tool_input),
        )
        if pre.deny is not None:
            return _vs_deny(pre.deny), 0
        if pre.command is not None and isinstance(tool_input, dict):
            spec: dict[str, Any] = {
                "hookEventName": "PreToolUse",
                "updatedInput": {**tool_input, "command": pre.command},
            }
            if pre.note is not None:
                spec["additionalContext"] = pre.note
            return {"hookSpecificOutput": spec}, 0
        return None, 0
    if name in ("UserPromptSubmit", "userPromptSubmitted"):
        cfg = config.load(payload.get("cwd"))
        if cfg.prompt_mode == "off":
            return None, 0
        found = guard.prompt_findings(sid, str(payload.get("prompt", "")))
        if found is None:
            return None, 0
        if cfg.prompt_mode == "block":
            return {"continue": False, "stopReason": guard.prompt_blocked(found)}, 0
        return {"systemMessage": guard.prompt_warning(found)}, 0
    if name in ("SessionEnd", "sessionEnd"):
        guard.end_session(sid)
    # PostToolUse: VS Code can't replace a result; shell output was already
    # masked by the wrapper, and unmaskable tools were denied before running.
    return None, 0


# -- entry points -------------------------------------------------------------------
def handle(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    if _is_vscode(payload):
        return _vscode(event, payload)
    return _cli(event, payload)


def fail(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    reason = "MaskFlow PII guard error. Ask the user to run `maskflow-agent doctor`."
    if _is_vscode(payload):
        if (payload.get("hook_event_name") or event) in ("PreToolUse", "preToolUse"):
            return _vs_deny(reason), 0
        return None, 0
    if event == "postToolUse":
        return {"modifiedResult": {"resultType": "success", "textResultForLlm": guard.WITHHELD}}, 0
    if event == "preToolUse":
        return {"permissionDecision": "deny", "permissionDecisionReason": reason}, 0
    return None, 0


# -- install ------------------------------------------------------------------------
FILE_NAME = "maskflow-agent.json"
# Found in a live test (Copilot CLI 1.0.97): a project's .github/hooks is
# skipped -- silently -- unless the folder is trusted, while
# ~/.copilot/hooks always loads.
INSTALL_NOTE = (
    "IMPORTANT: Copilot CLI loads a project's .github/hooks ONLY when the folder is "
    "trusted (run `copilot` here once and choose to trust it); otherwise these hooks "
    "are silently skipped and nothing is masked. `--scope user` (~/.copilot/hooks) "
    "always loads and is the safer choice on your own machine."
)
# Copilot lets a tool's original result through when an after-tool hook
# times out, so leave room for a cold engine start (ensure_daemon: 150 s).
_TIMEOUTS = {
    "sessionStart": 180,
    "preToolUse": 180,
    "postToolUse": 180,
    "userPromptSubmitted": 30,
    "sessionEnd": 5,
}


def config_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".copilot" / "hooks" / FILE_NAME
    return cwd / ".github" / "hooks" / FILE_NAME


def hooks_file(portable: bool = False) -> dict[str, Any]:
    """The whole hook file. `portable` runs `maskflow-agent` from PATH (for a
    committed file used on other machines or by the cloud agent) instead of
    this interpreter's absolute path."""
    hooks: dict[str, list[dict[str, Any]]] = {}
    for event in EVENTS:
        argv = ["hook", "--agent", "copilot", event]
        cmd = shlex.join(
            ["maskflow-agent", *argv]
            if portable
            else [sys.executable, "-m", "maskflow_agent", *argv]
        )
        hooks[event] = [
            {"type": "command", "bash": cmd, "command": cmd, "timeoutSec": _TIMEOUTS[event]}
        ]
    return {"version": 1, "hooks": hooks}


def install(path: Path, portable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hooks_file(portable), indent=2) + "\n", encoding="utf-8")


def uninstall(path: Path) -> bool:
    if not is_installed(path):
        return False
    path.unlink()
    return True


def is_installed(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return "maskflow_agent" in json.dumps(data) or "maskflow-agent hook" in json.dumps(data)


def probe(session_id: str, text: str) -> tuple[str, dict[str, Any]]:
    """A synthetic tool result for `maskflow-agent doctor` to push through
    this adapter."""
    return "postToolUse", {
        "sessionId": session_id,
        "toolName": "bash",
        "toolArgs": {"command": "cat kyc.csv"},
        "toolResult": {"resultType": "success", "textResultForLlm": text},
    }
