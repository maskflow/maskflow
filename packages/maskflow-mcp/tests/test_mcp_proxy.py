"""End-to-end: an in-process backend FastMCP behind the MaskFlow proxy."""

from __future__ import annotations

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client, FastMCP  # noqa: E402
from maskflow_mcp import build_proxy  # noqa: E402

pytestmark = pytest.mark.mcp

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"


def _backend() -> tuple[FastMCP, list[dict]]:
    seen: list[dict] = []
    backend = FastMCP("backend")

    @backend.tool
    def lookup(name: str, note: str) -> str:
        seen.append({"name": name, "note": note})
        return f"record for {name}: {note}"

    @backend.tool
    def echo_struct(value: str) -> dict:
        return {"echoed": value, "n": 1}

    @backend.resource("data://doc")
    def doc() -> str:
        return "public info, no PII"

    return backend, seen


@pytest.mark.asyncio
async def test_backend_sees_masked_args_client_sees_originals() -> None:
    backend, seen = _backend()
    async with Client(build_proxy(backend)) as c:
        r = await c.call_tool("lookup", {"name": "Ramesh Kumar", "note": f"PAN {PAN}"})

    assert seen[0]["name"] == "<PERSON_NAME_1>"
    assert seen[0]["note"] == "PAN <PAN_1>"
    assert r.content[0].text == f"record for Ramesh Kumar: PAN {PAN}"


@pytest.mark.asyncio
async def test_structured_content_unmasked() -> None:
    backend, _ = _backend()
    async with Client(build_proxy(backend)) as c:
        r = await c.call_tool("echo_struct", {"value": f"mail {EMAIL}"})
    assert r.structured_content == {"echoed": f"mail {EMAIL}", "n": 1}


@pytest.mark.asyncio
async def test_session_consistent_across_calls_on_one_connection() -> None:
    backend, seen = _backend()
    async with Client(build_proxy(backend)) as c:
        await c.call_tool("lookup", {"name": "Ramesh Kumar", "note": "a"})
        await c.call_tool("lookup", {"name": "Ramesh Kumar", "note": "b"})
    assert seen[0]["name"] == seen[1]["name"] == "<PERSON_NAME_1>"


@pytest.mark.asyncio
async def test_tools_list_passthrough() -> None:
    backend, _ = _backend()
    async with Client(build_proxy(backend)) as c:
        names = {t.name for t in await c.list_tools()}
    assert {"lookup", "echo_struct"} <= names


@pytest.mark.asyncio
async def test_resource_passthrough() -> None:
    backend, _ = _backend()
    async with Client(build_proxy(backend)) as c:
        content = await c.read_resource("data://doc")
    assert content[0].text == "public info, no PII"


@pytest.mark.asyncio
async def test_mask_tool_results_hides_new_pii_from_client() -> None:
    seen: list[dict] = []
    backend = FastMCP("backend")

    @backend.tool
    def fetch_customer(id: str) -> str:  # noqa: A002
        seen.append({"id": id})
        return f"Customer: Ramesh Kumar, email {EMAIL}"  # PII the tool introduced

    async with Client(build_proxy(backend, mask_tool_results=True)) as c:
        r = await c.call_tool("fetch_customer", {"id": "cust-1"})

    assert EMAIL not in r.content[0].text
    assert "<EMAIL_1>" in r.content[0].text


@pytest.mark.asyncio
async def test_default_does_not_mask_new_pii() -> None:
    backend = FastMCP("backend")

    @backend.tool
    def fetch() -> str:
        return f"email {EMAIL}"

    async with Client(build_proxy(backend)) as c:  # mask_tool_results=False
        r = await c.call_tool("fetch", {})
    assert r.content[0].text == f"email {EMAIL}"  # untouched
