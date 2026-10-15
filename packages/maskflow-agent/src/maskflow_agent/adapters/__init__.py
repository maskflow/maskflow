"""Hook adapters for agents other than Claude Code (whose adapter is
`maskflow_agent.hooks`). Stdlib only -- each hook is a fresh process.

    maskflow-agent hook --agent <name> <event>

An adapter translates its agent's hook payload into `guard` calls and the
result back into that agent's JSON. It never decides policy itself.

Every adapter module provides:

* `handle(event, payload) -> (stdout object or None, exit code)`
* `fail(event, payload) -> (stdout object or None, exit code)` -- the
  fail-closed answer used when `handle` raises: withhold the output of an
  after-tool event, deny a before-tool event.
* `EVENTS` -- the event names it accepts.

Support status is measured, not asserted: `STATUS` says whether the
adapter has passed a live test against the real agent ("verified") or has
only been built from the agent's documentation ("experimental").
"""

from __future__ import annotations

import importlib
import json
import sys
from types import ModuleType
from typing import Any

AGENTS = ("copilot", "cursor", "codex", "gemini", "antigravity")

STATUS: dict[str, str] = {agent: "experimental" for agent in AGENTS}


def load(agent: str) -> ModuleType:
    if agent not in AGENTS:
        raise KeyError(agent)
    return importlib.import_module(f"{__name__}.{agent}")


def _emit(obj: Any) -> None:
    if obj is not None:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False))
        sys.stdout.flush()


def main(agent: str, event: str) -> int:
    try:
        adapter = load(agent)
    except KeyError:
        sys.stderr.write(f"maskflow-agent: unknown agent {agent!r}\n")
        return 2
    if event not in adapter.EVENTS:
        sys.stderr.write(f"maskflow-agent: unknown {agent} hook {event!r}\n")
        return 2
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError
    except ValueError:
        _emit(adapter.fail(event, {})[0])  # unreadable payload: fail closed
        return 0
    try:
        out, code = adapter.handle(event, payload)
    except Exception:  # noqa: BLE001 -- last-resort fail-closed
        out, code = adapter.fail(event, payload)
    _emit(out)
    return int(code)
