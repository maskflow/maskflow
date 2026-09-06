"""Resolve a backend MCP server spec into something ``FastMCP.as_proxy``
accepts: a URL string, or a canonical single-server MCP config dict
(``{"mcpServers": {"backend": {...}}}``)."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any


def _looks_like_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def backend_from_command(command_line: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    parts = shlex.split(command_line)
    if not parts:
        raise ValueError("empty backend command")
    entry: dict[str, Any] = {"command": parts[0], "args": parts[1:]}
    if env:
        entry["env"] = env
    return {"mcpServers": {"backend": entry}}


def load_config_file(path: str | Path, backend_name: str | None = None) -> dict[str, Any]:
    """Read a Claude-Desktop-style config (``{"mcpServers": {...}}``) and
    return a single-server config dict."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    servers = data.get("mcpServers", data)
    if not isinstance(servers, dict) or not servers:
        raise ValueError(f"{path}: no mcpServers found")
    if backend_name is not None:
        if backend_name not in servers:
            raise ValueError(f"{path}: no server named {backend_name!r} (have: {sorted(servers)})")
        entry = servers[backend_name]
    elif len(servers) == 1:
        entry = next(iter(servers.values()))
    else:
        raise ValueError(
            f"{path} has {len(servers)} servers ({sorted(servers)}); pass --backend-name"
        )
    return {"mcpServers": {"backend": entry}}


def resolve_backend(
    *,
    backend: str | None,
    config_path: str | None,
    backend_name: str | None,
    pass_env: list[str] | None = None,
) -> str | dict[str, Any]:
    if config_path:
        return load_config_file(config_path, backend_name)
    if backend:
        if _looks_like_url(backend):
            return backend
        env = {k: os.environ[k] for k in (pass_env or []) if k in os.environ} or None
        return backend_from_command(backend, env)
    raise ValueError("pass --backend (a command line or URL) or --config <file>")
