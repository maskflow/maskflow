"""Shared Python side of the JavaScript plugin adapters (OpenCode, Cline).

Those agents extend through in-process JS plugins, not hook commands. The
installer writes a small plugin file that, for every tool call, runs
`maskflow-agent hook --agent <name> <event>` with a JSON payload, so the
policy stays here like every other adapter's. Protocol (stdin -> stdout):

    start   {session}                         -> {}
    before  {session, tool, input, cwd}       -> {} | {"input": {...}} | {"deny": "reason"}
    after   {session, tool, input, result}    -> {} | {"result": <masked, same shape>}
    end     {session}                         -> {}

The plugin itself fails closed: no answer, an unreadable answer or its own
time budget running out means deny before a tool and withhold after it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .. import guard

EVENTS = ("start", "before", "after", "end")


def session(payload: dict[str, Any]) -> str:
    sid = payload.get("session")
    if isinstance(sid, str) and sid:
        return sid
    cwd = str(payload.get("cwd") or "")
    return "plugin-" + hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16]


def shell_command(tool_input: Any) -> tuple[str | None, str | None]:
    if isinstance(tool_input, dict):
        for key in ("command", "cmd"):
            if isinstance(tool_input.get(key), str):
                return key, str(tool_input[key])
    return None, None


def handle(
    event: str, payload: dict[str, Any], kind_of: Any, shell_tools: frozenset[str]
) -> tuple[Any, int]:
    sid = session(payload)
    tool = str(payload.get("tool", ""))
    tool_input = payload.get("input")
    if event == "start":
        guard.ensure_daemon(sid)
        return {}, 0
    if event == "before":
        kind = kind_of(tool, tool_input)
        key, command = shell_command(tool_input) if kind == "shell" else (None, None)
        pre = guard.pre_tool(
            sid, kind=kind, tool_input=tool_input, command=command, cwd=payload.get("cwd")
        )
        if pre.deny is not None:
            return {"deny": pre.deny}, 0
        if pre.command is not None and key is not None and isinstance(tool_input, dict):
            return {"input": {**tool_input, key: pre.command}}, 0
        return {}, 0
    if event == "after":
        _, command = shell_command(tool_input) if tool in shell_tools else (None, None)
        masked = guard.mask_output(sid, payload.get("result"), command)
        return ({"result": masked} if masked is not None else {}), 0
    if event == "end":
        guard.end_session(sid)
    return {}, 0


def fail(event: str, payload: dict[str, Any]) -> tuple[Any, int]:
    if event == "after":
        return {"result": guard.withheld(payload.get("result", guard.WITHHELD))}, 0
    if event == "before":
        return {"deny": "MaskFlow PII guard error. Ask the user to run `maskflow-agent doctor`."}, 0
    return {}, 0


# -- plugin file ----------------------------------------------------------------------
_RUNNER = r"""
import { spawn } from "node:child_process";

const CMD = __CMD__;
const WITHHELD = __WITHHELD__;

// Same shape, every string replaced: what the model gets when the guard
// can't answer in time.
function withheld(value) {
  if (typeof value === "string") return value ? WITHHELD : value;
  if (Array.isArray(value)) return value.map(withheld);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, withheld(v)]));
  }
  return value;
}

// One guard call. Resolves to the parsed answer, or null on any failure
// (spawn error, non-zero exit, unreadable output, time budget exceeded).
function call(event, payload, budgetMs) {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(CMD[0], [...CMD.slice(1), event], { stdio: ["pipe", "pipe", "ignore"] });
    } catch {
      resolve(null);
      return;
    }
    const chunks = [];
    const timer = setTimeout(() => { child.kill("SIGKILL"); resolve(null); }, budgetMs);
    child.on("error", () => { clearTimeout(timer); resolve(null); });
    child.stdout.on("data", (c) => chunks.push(c));
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) return resolve(null);
      const text = Buffer.concat(chunks).toString("utf8").trim();
      try { resolve(text ? JSON.parse(text) : {}); } catch { resolve(null); }
    });
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify(payload));
  });
}

function startDetached(payload) {
  try {
    const child = spawn(CMD[0], [...CMD.slice(1), "start"],
      { stdio: ["pipe", "ignore", "ignore"], detached: true });
    child.on("error", () => {});
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify(payload));
    child.unref();
  } catch {}
}
"""


def plugin_source(body: str, command: list[str]) -> str:
    """A complete plugin file: the shared runner, then the agent's `body`."""
    header = (
        "// maskflow-agent: PII guard plugin. Generated by `maskflow-agent install`;\n"
        "// re-run it to update, `maskflow-agent uninstall` to remove.\n"
    )
    runner = _RUNNER.replace("__CMD__", json.dumps(command)).replace(
        "__WITHHELD__", json.dumps(guard.WITHHELD)
    )
    return header + runner + body


MARKER = "// maskflow-agent: PII guard plugin."


def write_plugin(path: Path, source: str) -> None:
    if path.exists() and not path.read_text(encoding="utf-8").startswith(MARKER):
        raise FileExistsError(f"{path} exists and is not a maskflow-agent plugin")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def is_ours(path: Path) -> bool:
    try:
        return path.read_text(encoding="utf-8").startswith(MARKER)
    except OSError:
        return False


def remove_plugin(path: Path) -> bool:
    if not is_ours(path):
        return False
    path.unlink()
    return True
