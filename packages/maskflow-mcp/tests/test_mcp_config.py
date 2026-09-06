"""config.resolve_backend / load_config_file (no fastmcp import needed)."""

from __future__ import annotations

import json

import pytest
from maskflow_mcp.config import backend_from_command, load_config_file, resolve_backend


def test_command_string_becomes_mcp_config() -> None:
    cfg = backend_from_command("npx -y @modelcontextprotocol/server-github")
    assert cfg == {
        "mcpServers": {
            "backend": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]}
        }
    }


def test_resolve_url_passes_through() -> None:
    assert (
        resolve_backend(backend="https://example.com/mcp", config_path=None, backend_name=None)
        == "https://example.com/mcp"
    )


def test_resolve_command_with_pass_env(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    cfg = resolve_backend(
        backend="server-github",
        config_path=None,
        backend_name=None,
        pass_env=["GITHUB_TOKEN", "MISSING"],
    )
    assert isinstance(cfg, dict)
    assert cfg["mcpServers"]["backend"]["env"] == {"GITHUB_TOKEN": "secret"}


def test_load_config_single_server(tmp_path) -> None:
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"mcpServers": {"gh": {"command": "server-github", "args": []}}}))
    assert load_config_file(p) == {
        "mcpServers": {"backend": {"command": "server-github", "args": []}}
    }


def test_load_config_multi_server_needs_name(tmp_path) -> None:
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"mcpServers": {"a": {"command": "a"}, "b": {"command": "b"}}}))
    with pytest.raises(ValueError, match="backend-name"):
        load_config_file(p)
    assert load_config_file(p, "b") == {"mcpServers": {"backend": {"command": "b"}}}


def test_resolve_nothing_raises() -> None:
    with pytest.raises(ValueError, match="--backend"):
        resolve_backend(backend=None, config_path=None, backend_name=None)
