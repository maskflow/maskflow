"""MaskflowMiddleware.on_call_tool with fakes for context / call_next."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("fastmcp")

from maskflow_mcp import MaskflowMiddleware, SessionRegistry  # noqa: E402

pytestmark = pytest.mark.mcp

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"


def _ctx(name: str, arguments: dict, session_id: str | None = "s1"):
    return SimpleNamespace(
        message=SimpleNamespace(name=name, arguments=arguments),
        fastmcp_context=SimpleNamespace(session_id=session_id),
    )


def _result(text: str = "", structured=None):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)] if text else [],
        structured_content=structured,
    )


@pytest.mark.asyncio
async def test_masks_args_then_unmasks_echoed_result() -> None:
    mw = MaskflowMiddleware()
    ctx = _ctx("t", {"note": f"PAN {PAN}"})

    async def call_next(c):
        # backend saw the masked value
        assert c.message.arguments["note"] == "PAN <PAN_1>"
        return _result(text="stored PAN <PAN_1>")

    r = await mw.on_call_tool(ctx, call_next)
    assert r.content[0].text == f"stored PAN {PAN}"
    mw.close()


@pytest.mark.asyncio
async def test_per_session_registry_keys_by_session_id() -> None:
    reg = SessionRegistry()
    mw = MaskflowMiddleware(registry=reg)

    async def call_next(c):
        return _result(text="ok")

    await mw.on_call_tool(_ctx("t", {"x": f"PAN {PAN}"}, session_id="a"), call_next)
    await mw.on_call_tool(_ctx("t", {"x": f"mail {EMAIL}"}, session_id="b"), call_next)
    # two different sessions were created
    assert len(reg._entries) == 2  # noqa: SLF001
    reg.close()


@pytest.mark.asyncio
async def test_mask_tool_results_flag() -> None:
    mw = MaskflowMiddleware(mask_tool_results=True)

    async def call_next(c):
        return _result(text=f"new customer {EMAIL}")

    r = await mw.on_call_tool(_ctx("t", {}), call_next)
    assert EMAIL not in r.content[0].text and "<EMAIL_1>" in r.content[0].text
    mw.close()


@pytest.mark.asyncio
async def test_missing_fastmcp_context_falls_back_to_default_key() -> None:
    mw = MaskflowMiddleware()
    ctx = SimpleNamespace(message=SimpleNamespace(name="t", arguments={"x": f"PAN {PAN}"}))

    async def call_next(c):
        assert c.message.arguments["x"] == "PAN <PAN_1>"
        return _result(text="ok")

    await mw.on_call_tool(ctx, call_next)
    mw.close()
