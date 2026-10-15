"""Cline (CLI, SDK and Kanban; Cline's plugins don't run in its VS Code or
JetBrains extensions). A plugin file in `.cline/plugins/` (project) or
`~/.cline/plugins/` (global). Its `afterTool` hook can replace any tool's
result, so Cline gets after-the-fact masking for every tool.

Cline gives each plugin hook 3 seconds and, by default, ignores a hook
that times out -- the original result would then reach the model. So the
plugin keeps its own 2.5 s budget and withholds the result itself when the
guard doesn't answer in time, and starts the guard in the background when
a session begins so later calls are fast.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import _jsplugin

EVENTS = _jsplugin.EVENTS
_SHELL = frozenset({"run_commands", "run_command", "execute_command", "bash", "shell"})
_WRITE_HINTS = ("write", "edit", "patch", "replace", "editor")
FILE_NAME = "maskflow-agent.js"

_BODY = r"""
const BUDGET_MS = 2500;  // Cline's own hook timeout is 3 s
const STARTING = "MaskFlow PII guard is starting or unavailable; retry this tool call "
  + "in a few seconds. If it keeps failing, ask the user to run `maskflow-agent doctor`.";
let SESSION = null;
let CWD = null;

const plugin = {
  name: "maskflow-agent",
  manifest: { capabilities: ["hooks"] },
  setup(api, ctx) {
    SESSION = ctx?.session?.sessionId ?? null;
    CWD = ctx?.cwd ?? null;
    startDetached({ session: SESSION, cwd: CWD });
  },
  hooks: {
    async beforeTool(context) {
      const tool = context?.toolCall?.name ?? context?.tool?.name ?? "";
      const answer = await call("before",
        { session: SESSION, tool, input: context?.input, cwd: CWD }, BUDGET_MS);
      if (answer === null) return { skip: true, reason: STARTING };
      if (answer.deny) return { skip: true, reason: answer.deny };
      if (answer.input) return { input: answer.input };
      return undefined;
    },
    async afterTool(context) {
      const tool = context?.toolCall?.name ?? context?.tool?.name ?? "";
      const answer = await call("after",
        { session: SESSION, tool, input: context?.input, result: context?.result, cwd: CWD },
        BUDGET_MS);
      if (answer === null) return { result: withheld(context?.result) };
      if (answer.result !== undefined) return { result: answer.result };
      return undefined;
    },
  },
};

export default plugin;
"""


def _kind(tool: str, tool_input: Any) -> str:
    name = tool.lower()
    if tool in _SHELL:
        return "shell"
    if any(hint in name for hint in _WRITE_HINTS):
        return "write"
    return "other"


def handle(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    return _jsplugin.handle(event, payload, _kind, _SHELL)


fail = _jsplugin.fail


def config_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".cline" / "plugins" / FILE_NAME
    return cwd / ".cline" / "plugins" / FILE_NAME


def _command(portable: bool) -> list[str]:
    tail = ["hook", "--agent", "cline"]
    return (
        ["maskflow-agent", *tail] if portable else [sys.executable, "-m", "maskflow_agent", *tail]
    )


def install(path: Path, portable: bool = False) -> None:
    _jsplugin.write_plugin(path, _jsplugin.plugin_source(_BODY, _command(portable)))


def uninstall(path: Path) -> bool:
    return _jsplugin.remove_plugin(path)


def is_installed(path: Path) -> bool:
    return _jsplugin.is_ours(path)


def probe(session_id: str, text: str) -> tuple[str, dict[str, Any]]:
    return "after", {
        "session": session_id,
        "tool": "run_commands",
        "input": {"command": "cat kyc.csv"},
        "result": text,
    }
