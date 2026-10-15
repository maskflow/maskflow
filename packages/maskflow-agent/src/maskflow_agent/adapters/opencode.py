"""OpenCode. A local plugin file (`.opencode/plugins/maskflow-agent.js`, or
`~/.config/opencode/plugins/` for every project) that OpenCode loads at
start-up. Its `tool.execute.after` hook can replace any tool's output, so
OpenCode gets after-the-fact masking for every tool, as Claude Code does.

* `tool.execute.before`: placeholder writes are refused (the hook throws);
  allowlisted commands get the ticketed run-time restore (`output.args`).
* `tool.execute.after`: `output.output` (what the model reads) and the
  bash tool's `metadata.output` are masked; with no answer from the guard
  they are withheld.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import _jsplugin

EVENTS = _jsplugin.EVENTS
_SHELL = frozenset({"bash"})
_WRITE = {"write", "edit", "patch", "multiedit"}
FILE_NAME = "maskflow-agent.js"

_BODY = r"""
const BUDGET_MS = 180000;

export const MaskflowAgent = async ({ directory }) => ({
  "tool.execute.before": async (input, output) => {
    const answer = await call("before",
      { session: input.sessionID, tool: input.tool, input: output.args, cwd: directory },
      BUDGET_MS);
    if (answer === null) {
      throw new Error("MaskFlow PII guard error. Ask the user to run `maskflow-agent doctor`.");
    }
    if (answer.deny) throw new Error(answer.deny);
    if (answer.input) {
      for (const key of Object.keys(output.args)) delete output.args[key];
      Object.assign(output.args, answer.input);
    }
  },
  "tool.execute.after": async (input, output) => {
    const result = { output: output.output, metadata_output: output.metadata?.output };
    const answer = await call("after",
      { session: input.sessionID, tool: input.tool, input: input.args, result }, BUDGET_MS);
    const masked = answer === null ? withheld(result) : answer.result;
    if (masked === undefined) return;
    output.output = masked.output;
    if (output.metadata && typeof output.metadata.output === "string") {
      output.metadata.output = masked.metadata_output;
    }
  },
  event: async ({ event }) => {
    const session = event.properties?.info?.id;
    if (event.type === "session.created") startDetached({ session });
    if (event.type === "session.deleted") await call("end", { session }, 3000);
  },
});
"""


def _kind(tool: str, tool_input: Any) -> str:
    if tool in _SHELL:
        return "shell"
    if tool in _WRITE:
        return "write"
    return "other"


def handle(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    return _jsplugin.handle(event, payload, _kind, _SHELL)


fail = _jsplugin.fail


def config_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".config" / "opencode" / "plugins" / FILE_NAME
    return cwd / ".opencode" / "plugins" / FILE_NAME


def _command(portable: bool) -> list[str]:
    tail = ["hook", "--agent", "opencode"]
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
        "tool": "bash",
        "input": {"command": "cat kyc.csv"},
        "result": {"output": text, "metadata_output": text},
    }
