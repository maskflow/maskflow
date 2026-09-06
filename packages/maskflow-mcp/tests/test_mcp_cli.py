"""CLI argument wiring (build the proxy, don't run it)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastmcp")

from maskflow_mcp import cli  # noqa: E402

pytestmark = pytest.mark.mcp


def test_build_from_backend_command() -> None:
    args = cli.argparse.Namespace(
        transport="stdio",
        backend="server-github --flag",
        config=None,
        backend_name=None,
        pass_env=[],
        min_confidence=0.6,
        patterns_only=True,
        mask_tool_results=False,
        session_ttl=1800.0,
        name="maskflow-mcp",
    )
    proxy = cli._build(args)  # noqa: SLF001
    assert proxy is not None


def test_build_from_config_file(tmp_path) -> None:
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"mcpServers": {"gh": {"command": "server-github", "args": []}}}))
    args = cli.argparse.Namespace(
        transport="stdio",
        backend=None,
        config=str(p),
        backend_name="gh",
        pass_env=[],
        min_confidence=None,
        patterns_only=False,
        mask_tool_results=True,
        session_ttl=3600.0,
        name="x",
    )
    assert cli._build(args) is not None  # noqa: SLF001


def test_main_reports_missing_backend() -> None:
    rc = cli.main(["stdio"])
    assert rc == 2


def test_help_lists_transports(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "stdio" in out and "http" in out
