"""``maskflow-mcp`` -- run a PII-masking MCP proxy in front of a backend
server.

    # stdio (Claude Desktop, most agents): wrap a stdio server
    maskflow-mcp stdio --backend "npx -y @modelcontextprotocol/server-github"

    # from a Claude-Desktop-style config file
    maskflow-mcp stdio --config ./mcp.json --backend-name github

    # HTTP: wrap a remote server, expose locally over HTTP
    maskflow-mcp http --backend https://example.com/mcp --port 9000
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from fastmcp import FastMCP

from .config import resolve_backend
from .proxy import build_proxy


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", help="backend command line, or a URL")
    p.add_argument("--config", help="Claude-Desktop-style JSON config file")
    p.add_argument("--backend-name", help="server name to use from --config")
    p.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="VAR",
        help="env var to forward to a stdio backend (repeatable)",
    )
    p.add_argument("--min-confidence", type=float, default=None)
    p.add_argument(
        "--patterns-only",
        action="store_true",
        help="skip the spaCy NER pass (faster; drops bare-name / address detection)",
    )
    p.add_argument(
        "--mask-tool-results",
        action="store_true",
        help="also mask raw PII the tool *introduced* in its result (default: only "
        "unmask placeholders the tool echoed)",
    )
    p.add_argument("--session-ttl", type=float, default=3600.0, metavar="SECONDS")
    p.add_argument("--name", default="maskflow-mcp")


def _build(args: argparse.Namespace) -> FastMCP:
    backend = resolve_backend(
        backend=args.backend,
        config_path=args.config,
        backend_name=args.backend_name,
        pass_env=args.pass_env,
    )
    return build_proxy(
        backend,
        name=args.name,
        min_confidence=args.min_confidence,
        patterns_only=args.patterns_only,
        mask_tool_results=args.mask_tool_results,
        session_ttl_seconds=args.session_ttl,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maskflow-mcp", description=__doc__)
    sub = parser.add_subparsers(dest="transport", required=True)

    p_stdio = sub.add_parser("stdio", help="serve over stdio (default for agents)")
    _add_common(p_stdio)

    p_http = sub.add_parser("http", help="serve over Streamable HTTP")
    _add_common(p_http)
    p_http.add_argument("--host", default="127.0.0.1")
    p_http.add_argument("--port", type=int, default=8080)
    p_http.add_argument("--path", default="/mcp")

    args = parser.parse_args(argv)
    try:
        proxy = _build(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"maskflow-mcp: {exc}", file=sys.stderr)
        return 2

    if args.transport == "stdio":
        proxy.run(transport="stdio")
    else:
        proxy.run(transport="http", host=args.host, port=args.port, path=args.path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
