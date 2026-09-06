"""MaskFlow release rule #1: raw PII never reaches the wire to the backend
server, nor logs / repr."""

from __future__ import annotations

import json
import logging

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client, FastMCP  # noqa: E402
from maskflow_mcp import MaskflowMiddleware, build_proxy  # noqa: E402
from maskflow_mcp._masking import mask_arguments  # noqa: E402

pytestmark = pytest.mark.mcp

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"
MOBILE = "9812345678"
SECRETS = (PAN, EMAIL, MOBILE)


def _clean(blob: str) -> None:
    for s in SECRETS:
        assert s not in blob


@pytest.mark.leak
@pytest.mark.asyncio
async def test_backend_never_receives_a_raw_value() -> None:
    seen_raw: list[str] = []
    backend = FastMCP("backend")

    @backend.tool
    def sink(payload: str, meta: dict) -> str:
        seen_raw.append(json.dumps({"payload": payload, "meta": meta}))
        return "ok"

    async with Client(build_proxy(backend)) as c:
        await c.call_tool(
            "sink",
            {"payload": f"PAN {PAN}, mail {EMAIL}", "meta": {"mobile": f"mobile {MOBILE}"}},
        )
    _clean("".join(seen_raw))


@pytest.mark.leak
@pytest.mark.asyncio
async def test_middleware_debug_logging_has_no_pii(caplog: pytest.LogCaptureFixture) -> None:
    import maskflow

    mw = MaskflowMiddleware()
    from types import SimpleNamespace

    ctx = SimpleNamespace(
        message=SimpleNamespace(name="t", arguments={"x": f"PAN {PAN} mail {EMAIL}"}),
        fastmcp_context=SimpleNamespace(session_id="s"),
    )

    async def call_next(c):
        return SimpleNamespace(content=[SimpleNamespace(text="ok")], structured_content=None)

    with caplog.at_level(logging.DEBUG):
        await mw.on_call_tool(ctx, call_next)
    _clean(caplog.text)
    mw.close()
    del maskflow


@pytest.mark.leak
def test_mask_arguments_output_has_no_originals() -> None:
    import maskflow

    s = maskflow.session(ttl_seconds=None, config=maskflow.RootConfig())
    out = mask_arguments(s, {"a": f"PAN {PAN}", "b": {"c": f"mail {EMAIL}"}})
    _clean(json.dumps(out))
