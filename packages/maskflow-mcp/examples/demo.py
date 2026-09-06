"""Runnable demo: the MaskFlow proxy in front of a toy backend, no subprocess.

    pip install maskflow-mcp
    python packages/maskflow-mcp/examples/demo.py

Shows the backend receiving masked arguments and the client receiving the
originals restored.
"""

from __future__ import annotations

import asyncio

from echo_backend import server as backend
from fastmcp import Client
from maskflow_mcp import build_proxy


async def main() -> None:
    proxy = build_proxy(backend, name="maskflow-mcp-demo")

    async with Client(proxy) as client:
        result = await client.call_tool(
            "file_ticket",
            {
                "customer": "Ramesh Kumar",
                "summary": "Refund request for PAN ABCPE1234F",
                "contact": "ramesh@example.com",
            },
        )
        print("client receives (restored):")
        print(" ", result.structured_content)


if __name__ == "__main__":
    asyncio.run(main())
