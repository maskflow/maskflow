"""Google Antigravity (CLI `agy` and the Antigravity IDE). Hooks:
`.agents/hooks.json` (workspace) or `~/.gemini/config/hooks.json` (global).

Antigravity's `PreToolUse` can rewrite a tool's arguments (`overwrite`, a
shallow merge into `toolCall.args`), but its `PostToolUse` returns nothing
the agent acts on. So Antigravity runs in wrap mode:

* `run_command` is rewritten into the mask-only wrapper; allowlisted
  commands with placeholders get the ticketed run-time restore;
* `grep_search` is denied with a hint to search through the shell;
* `view_file` is denied when the file holds personal data;
* MCP tools are denied, with a pointer to the `maskflow-mcp` proxy.

`decision: "allow"` hands the call on to the next hook or the default
policy, which still prompts if it would have. Only `auto_approve` skips a
prompt, and the guard never returns it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import guard
from . import _files

EVENTS = ("SessionStart", "PreToolUse", "Stop")

_SHELL = {"run_command"}
_WRITE = {"write_to_file", "replace_file_content", "multi_replace_file_content"}
_READ = {"view_file"}
_SEARCH = {"grep_search"}
_MCP_DENIED = (
    "MaskFlow PII guard: Antigravity's hooks can't mask MCP tool results. Route "
    "this MCP server through the `maskflow-mcp` proxy so its results are masked."
)
HOOK_NAME = "maskflow-agent"


def _kind(tool: str) -> str:
    if tool in _SHELL:
        return "shell"
    if tool in _WRITE:
        return "write"
    if tool in _READ:
        return "read"
    if tool in _SEARCH:
        return "search"
    if tool.lower().startswith("mcp"):
        return "mcp"
    return "other"


def _deny(reason: str) -> dict[str, Any]:
    return {"decision": "deny", "reason": reason}


def handle(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    sid = str(payload.get("conversationId") or "")
    if not sid:
        return fail(event, payload)
    if event == "SessionStart":
        guard.ensure_daemon(sid, payload.get("transcriptPath"))
        return {}, 0
    if event == "PreToolUse":
        call = payload.get("toolCall") or {}
        tool = str(call.get("name", ""))
        raw_args = call.get("args")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        kind = _kind(tool)
        if kind == "mcp":
            return _deny(_MCP_DENIED), 0
        command = args.get("CommandLine")
        path = args.get("AbsolutePath")
        pre = guard.pre_tool(
            sid,
            kind=kind,
            tool_input=args,
            command=command if isinstance(command, str) else None,
            transcript_path=payload.get("transcriptPath"),
            cwd=args.get("Cwd") if isinstance(args.get("Cwd"), str) else None,
            wrap_all=True,
            read_path=path if isinstance(path, str) else None,
        )
        if pre.deny is not None:
            return _deny(pre.deny), 0
        if pre.command is not None:
            return {"decision": "allow", "overwrite": {"CommandLine": pre.command}}, 0
        return {"decision": "allow"}, 0
    if event == "Stop":
        guard.end_session(sid)
    return {}, 0


def fail(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    if event == "PreToolUse":
        return _deny("MaskFlow PII guard error. Ask the user to run `maskflow-agent doctor`."), 0
    return {}, 0


# -- install ------------------------------------------------------------------------
_TIMEOUTS = {"SessionStart": 180, "PreToolUse": 180, "Stop": 5}


def config_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".gemini" / "config" / "hooks.json"
    return cwd / ".agents" / "hooks.json"


def install(path: Path, portable: bool = False) -> None:
    """hooks.json is keyed by hook name; ours is the `maskflow-agent` entry."""
    data = _files.load(path)
    entry: dict[str, Any] = {}
    for event in EVENTS:
        handler = {
            "type": "command",
            "command": _files.command("antigravity", event, portable),
            "timeout": _TIMEOUTS[event],
        }
        entry[event] = (
            [{"matcher": "*", "hooks": [handler]}] if event == "PreToolUse" else [handler]
        )
    data[HOOK_NAME] = entry
    _files.write(path, data)


def uninstall(path: Path) -> bool:
    if not is_installed(path):
        return False
    data = _files.load(path)
    del data[HOOK_NAME]
    if data:
        _files.write(path, data)
    else:
        path.unlink()
    return True


def is_installed(path: Path) -> bool:
    try:
        return _files.has_groups(_files.load(path).get(HOOK_NAME), "antigravity")
    except (OSError, ValueError):
        return False


def probe(session_id: str, text: str) -> tuple[str, dict[str, Any]]:
    """Wrap mode masks through the shell wrapper, so the probe is a shell
    call that prints `text`; doctor runs the rewritten command (`rewritten`)
    and checks its output."""
    import shlex

    return "PreToolUse", {
        "conversationId": session_id,
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": f"printf '%s' {shlex.quote(text)}"},
        },
    }


def rewritten(out: Any) -> str | None:
    command = (out.get("overwrite") or {}).get("CommandLine") if isinstance(out, dict) else None
    return command if isinstance(command, str) else None
