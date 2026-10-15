"""Installing hooks into agents' JSON config files without disturbing
anything else in them. Ours are recognised by `--agent <name>` in the
command line, so uninstall removes exactly those."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any


def command(agent: str, event: str, portable: bool) -> str:
    """The hook command line. `portable` runs `maskflow-agent` from PATH (for
    a committed file used on other machines) instead of this interpreter's
    absolute path."""
    argv = ["hook", "--agent", agent, event]
    if portable:
        return shlex.join(["maskflow-agent", *argv])
    return shlex.join([sys.executable, "-m", "maskflow_agent", *argv])


def marker(agent: str) -> str:
    return f"--agent {agent} "


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _ours(handler: Any, agent: str) -> bool:
    return isinstance(handler, dict) and marker(agent) in str(handler.get("command", "")) + " "


# -- Claude-style files: {event: [{"matcher"?: ..., "hooks": [handler, ...]}]} ----------
def strip_groups(hooks: dict[str, Any], agent: str) -> None:
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                handlers = [h for h in group["hooks"] if not _ours(h, agent)]
                if handlers:
                    kept.append({**group, "hooks": handlers})
            elif not _ours(group, agent):
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]


def has_groups(hooks: Any, agent: str) -> bool:
    if not isinstance(hooks, dict):
        return False
    for groups in hooks.values():
        for group in groups if isinstance(groups, list) else []:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if isinstance(handlers, list) and any(_ours(h, agent) for h in handlers):
                return True
            if _ours(group, agent):
                return True
    return False
