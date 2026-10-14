"""`maskflow-agent install` / `uninstall`: add or remove the guard's hooks in
a Claude Code settings file, leaving every other setting and hook alone.

Hooks use the exec form (`command` + `args`, no shell) with this
interpreter's absolute path, so they keep working whatever PATH the hook
process gets. Ours are recognised by the `maskflow_agent` module in their
args -- uninstall removes exactly those.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_MARKER = "maskflow_agent"

# (event, matcher, hook name, timeout seconds, extra handler fields)
_HOOKS: list[tuple[str, str | None, str, int, dict[str, Any]]] = [
    # 180 s: room for a cold engine start (hooks.ensure_daemon waits 150 s).
    ("SessionStart", None, "session-start", 180, {}),
    # onFailure "block": if this hook can't run, the tool doesn't either.
    ("PreToolUse", "*", "pre-tool-use", 180, {"onFailure": "block"}),
    ("PostToolUse", "*", "post-tool-use", 120, {}),
    ("UserPromptSubmit", None, "user-prompt-submit", 30, {}),
    ("SessionEnd", None, "session-end", 2, {}),
]


def warm_up() -> tuple[bool, float]:
    """Load the masking engine once in a child process so the first Claude
    Code session doesn't pay the cold start (bytecode compile + spaCy load,
    ~26 s on a fresh install, ~2 s afterwards)."""
    import os
    import subprocess
    import time

    # maskflow_core's config loader rejects unknown MASKFLOW_* variables --
    # same reason the daemon strips ours before importing the engine.
    env = {k: v for k, v in os.environ.items() if not k.startswith("MASKFLOW_AGENT_")}
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-c", "import maskflow; maskflow.Session().mask('warm-up')"],
        capture_output=True,
        timeout=600,
        check=False,
        env=env,
    )
    return proc.returncode == 0, time.monotonic() - started


def settings_path(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    if scope == "local":
        return cwd / ".claude" / "settings.local.json"
    return cwd / ".claude" / "settings.json"


def _handler(name: str, timeout: int, extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "command",
        "command": sys.executable,
        "args": ["-m", _MARKER, "hook", name],
        "timeout": timeout,
        **extra,
    }


def _is_ours(handler: Any) -> bool:
    return isinstance(handler, dict) and _MARKER in " ".join(
        str(a) for a in [handler.get("command", ""), *handler.get("args", [])]
    )


def _strip(settings: dict[str, Any]) -> dict[str, Any]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            if not isinstance(group, dict):
                kept.append(group)
                continue
            handlers = [h for h in group.get("hooks", []) if not _is_ours(h)]
            if handlers:
                kept.append({**group, "hooks": handlers})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]
    return settings


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def install(path: Path) -> dict[str, Any]:
    settings = _strip(_load(path))
    hooks = settings.setdefault("hooks", {})
    for event, matcher, name, timeout, extra in _HOOKS:
        group: dict[str, Any] = {"hooks": [_handler(name, timeout, extra)]}
        if matcher is not None:
            group = {"matcher": matcher, **group}
        hooks.setdefault(event, []).append(group)
    _write(path, settings)
    return settings


def uninstall(path: Path) -> bool:
    if not path.exists():
        return False
    before = _load(path)
    after = _strip(json.loads(json.dumps(before)))
    if after == before:
        return False
    _write(path, after)
    return True


def installed(path: Path) -> list[str]:
    """Events that have our hook in `path`."""
    try:
        hooks = _load(path).get("hooks", {})
    except (OSError, ValueError):
        return []
    found = []
    for event, groups in hooks.items() if isinstance(hooks, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            if isinstance(group, dict) and any(_is_ours(h) for h in group.get("hooks", [])):
                found.append(event)
    return sorted(set(found))


def _write(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


EXPECTED_EVENTS = sorted({event for event, *_ in _HOOKS})
