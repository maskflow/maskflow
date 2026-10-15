"""Devin Desktop (formerly Windsurf; Cascade). Hooks: `.devin/hooks.json`
(workspace) or `~/.codeium/windsurf/hooks.json` (user).

Cascade's hooks can only block (exit code 2, with stderr shown to the
agent) or observe. They can't rewrite a command or a result. So this
adapter is a gate:

* `pre_run_command` blocks every command that isn't already in the exact
  mask-only wrapper form for this conversation, and tells the agent the
  exact command to run instead. The wrapper masks the output and restores
  nothing, so placeholders can't be restored in Devin Desktop;
* `pre_read_code` blocks a file holding personal data and gives the
  wrapped `cat` to run instead;
* `pre_mcp_tool_use` blocks MCP tools, pointing to the `maskflow-mcp` proxy;
* `pre_write_code` blocks edits containing placeholders.

Any exit code other than 2 lets the action through, including a crash, so
every failure path here exits 2.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any

from .. import config, guard
from . import _files

EVENTS = (
    "pre_run_command",
    "pre_read_code",
    "pre_mcp_tool_use",
    "pre_write_code",
    "pre_user_prompt",
)
BLOCK = 2
_MCP_DENIED = (
    "MaskFlow PII guard: Devin Desktop's hooks can't mask MCP tool results. Route "
    "this MCP server through the `maskflow-mcp` proxy so its results are masked."
)


def _block(message: str) -> tuple[None, int]:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
    return None, BLOCK


def _info(payload: dict[str, Any]) -> dict[str, Any]:
    info = payload.get("tool_info")
    return info if isinstance(info, dict) else payload


def handle(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    sid = str(payload.get("trajectory_id") or "")
    if not sid:
        return fail(event, payload)
    info = _info(payload)
    if event == "pre_user_prompt":
        cfg = config.load(info.get("cwd") if isinstance(info.get("cwd"), str) else None)
        if cfg.prompt_mode != "block":
            return None, 0  # a warning has no channel here: only blocking does
        found = guard.prompt_findings(sid, str(info.get("user_prompt", "")))
        return _block(guard.prompt_blocked(found)) if found else (None, 0)
    if not guard.ensure_daemon(sid):
        return _block(guard.GUARD_DOWN)
    if event == "pre_run_command":
        command = info.get("command_line")
        if not isinstance(command, str):
            return _block("MaskFlow PII guard: unreadable command.")
        if guard.is_mask_only_command(sid, command):
            return None, 0
        return _block(
            "MaskFlow PII guard: commands run only through the masking wrapper, which "
            "masks personal data in their output (placeholders are not restored). "
            "Run exactly this instead:\n" + guard.mask_only_command(sid, command)
        )
    if event == "pre_read_code":
        path = info.get("file_path")
        pre = guard.pre_tool(
            sid,
            kind="read",
            tool_input={},
            wrap_all=True,
            read_path=path if isinstance(path, str) else None,
        )
        if pre.deny is None:
            return None, 0
        cat = guard.mask_only_command(sid, f"cat {shlex.quote(str(path))}")
        return _block(
            "MaskFlow PII guard: this file contains personal data and Devin's file "
            "reader can't mask it. Read it through the masking wrapper instead:\n" + cat
        )
    if event == "pre_mcp_tool_use":
        return _block(_MCP_DENIED)
    if event == "pre_write_code":
        pre = guard.pre_tool(sid, kind="write", tool_input=info.get("edits") or [])
        return _block(pre.deny) if pre.deny is not None else (None, 0)
    return None, 0


def fail(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    if event == "pre_user_prompt":
        return None, 0  # prompts are advisory
    return _block("MaskFlow PII guard error. Ask the user to run `maskflow-agent doctor`.")


# -- install ------------------------------------------------------------------------
def config_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".codeium" / "windsurf" / "hooks.json"
    return cwd / ".devin" / "hooks.json"


def install(path: Path, portable: bool = False) -> None:
    data = _files.load(path)
    hooks = data.setdefault("hooks", {})
    for event in EVENTS:
        entries = hooks.get(event)
        kept = [e for e in entries if not _ours(e)] if isinstance(entries, list) else []
        hooks[event] = [
            *kept,
            {"command": _files.command("devin", event, portable), "show_output": False},
        ]
    _files.write(path, data)


def _ours(entry: Any) -> bool:
    return isinstance(entry, dict) and _files.marker("devin") in str(entry.get("command")) + " "


def uninstall(path: Path) -> bool:
    if not is_installed(path):
        return False
    data = _files.load(path)
    hooks = data["hooks"]
    for event in list(hooks):
        if isinstance(hooks[event], list):
            hooks[event] = [e for e in hooks[event] if not _ours(e)]
            if not hooks[event]:
                del hooks[event]
    if not hooks:
        del data["hooks"]
    if data:
        _files.write(path, data)
    else:
        path.unlink()
    return True


def is_installed(path: Path) -> bool:
    try:
        hooks = _files.load(path).get("hooks")
    except (OSError, ValueError):
        return False
    return isinstance(hooks, dict) and any(
        _ours(e) for entries in hooks.values() if isinstance(entries, list) for e in entries
    )


def probe(session_id: str, text: str) -> tuple[str, dict[str, Any]]:
    return "pre_run_command", {
        "trajectory_id": session_id,
        "agent_action_name": "pre_run_command",
        "tool_info": {"command_line": f"printf '%s' {shlex.quote(text)}", "cwd": "/tmp"},
    }


def rewritten(out: Any, stderr: str = "") -> str | None:
    """The wrapped command the gate told the agent to run (last stderr line)."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines and "--mask-only" in lines[-1] else None
