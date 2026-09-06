"""A toy backend MCP server: a `file_ticket` tool that echoes its arguments.

Run it behind the proxy:

    maskflow-mcp stdio --backend "python packages/maskflow-mcp/examples/echo_backend.py"
"""

from __future__ import annotations

from fastmcp import FastMCP

server = FastMCP("echo-backend")


@server.tool
def file_ticket(customer: str, summary: str, contact: str) -> dict:
    """Pretend to file a support ticket; echo what we received."""
    import sys

    print(
        f"[backend] received customer={customer!r} contact={contact!r}",
        file=sys.stderr,
    )
    return {
        "status": "filed",
        "ticket": f"Ticket for {customer}: {summary}",
        "notify": contact,
    }


if __name__ == "__main__":
    server.run(transport="stdio")
