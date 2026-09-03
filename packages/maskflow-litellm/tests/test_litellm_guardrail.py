"""Integration tests for the CustomGuardrail adapter against the real
litellm base class and response types.

Run with: uv run --group litellm pytest packages/maskflow-litellm -m litellm
"""

from __future__ import annotations

import pytest

pytest.importorskip("litellm")

import litellm  # noqa: E402
from litellm.caching.caching import DualCache  # noqa: E402
from litellm.proxy._types import UserAPIKeyAuth  # noqa: E402
from litellm.types.utils import (  # noqa: E402
    Delta,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
)
from maskflow_litellm import MaskflowGuardrail  # noqa: E402

pytestmark = pytest.mark.litellm

PAN = "ABCPE1234F"  # synthetic, structurally valid
EMAIL = "alice@example.com"


def _guardrail(**kw) -> MaskflowGuardrail:
    kw.setdefault("guardrail_name", "mf")
    kw.setdefault("event_hook", ["pre_call", "post_call"])
    # These tests exercise the adapter wiring, not detection quality -- the
    # deterministic identifier path (PAN/email) is enough and needs no spaCy.
    kw.setdefault("maskflow_patterns_only", True)
    return MaskflowGuardrail(**kw)


def _req(content: str, **extra) -> dict:
    return {
        "guardrails": ["mf"],
        "litellm_call_id": "call-abc",
        "messages": [{"role": "user", "content": content}],
        **extra,
    }


def _text_response(content: str) -> ModelResponse:
    return ModelResponse(
        choices=[{"index": 0, "message": {"role": "assistant", "content": content}}]
    )


async def _run_stream(guardrail, request_data, fragments):
    async def source():
        for frag in fragments:
            yield ModelResponseStream(
                choices=[StreamingChoices(index=0, delta=Delta(content=frag))]
            )
        yield ModelResponseStream(
            choices=[StreamingChoices(index=0, delta=Delta(), finish_reason="stop")]
        )

    out = []
    async for chunk in guardrail.async_post_call_streaming_iterator_hook(
        UserAPIKeyAuth(), source(), request_data
    ):
        piece = chunk.choices[0].delta.content
        if isinstance(piece, str):
            out.append(piece)
    return "".join(out)


@pytest.mark.asyncio
async def test_pre_call_masks_messages_and_sets_ref() -> None:
    g = _guardrail()
    data = _req(f"my PAN is {PAN}")
    out = await g.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), data, "completion")
    assert PAN not in out["messages"][0]["content"]
    assert "<PAN_1>" in out["messages"][0]["content"]
    assert out["metadata"]["maskflow_ref"].startswith("c:")


@pytest.mark.asyncio
async def test_round_trip_non_streaming() -> None:
    g = _guardrail()
    data = _req(f"my PAN is {PAN}")
    await g.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), data, "completion")
    masked_token = data["messages"][0]["content"].split()[-1]

    response = _text_response(f"Filed return for {masked_token}.")
    result = await g.async_post_call_success_hook(data, UserAPIKeyAuth(), response)
    assert result.choices[0].message.content == f"Filed return for {PAN}."


@pytest.mark.asyncio
async def test_round_trip_streaming() -> None:
    g = _guardrail()
    data = _req(f"contact {EMAIL}")
    await g.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), data, "completion")
    data["stream"] = True
    token = data["messages"][0]["content"].split()[-1]

    # split the placeholder across two fragments
    reply = f"Reached {token} ok"
    cut = reply.index(token) + 3
    assert await _run_stream(g, data, [reply[:cut], reply[cut:]]) == f"Reached {EMAIL} ok"


@pytest.mark.asyncio
async def test_streaming_response_not_double_unmasked_in_success_hook() -> None:
    g = _guardrail()
    data = _req(f"contact {EMAIL}")
    await g.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), data, "completion")
    data["stream"] = True
    # success hook must be a no-op for stream=True (iterator hook owns it)
    response = _text_response("nothing to do")
    result = await g.async_post_call_success_hook(data, UserAPIKeyAuth(), response)
    assert result.choices[0].message.content == "nothing to do"


@pytest.mark.asyncio
async def test_cross_turn_session_keeps_token_identity() -> None:
    g = _guardrail()
    md = {"metadata": {"maskflow_session_id": "conv-7"}}

    d1 = _req(f"my PAN is {PAN}", **md)
    await g.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), d1, "completion")
    tok1 = d1["messages"][0]["content"].split()[-1]

    d2 = _req(f"remind me, PAN {PAN}?", litellm_call_id="call-def", **md)
    await g.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), d2, "completion")
    tok2 = d2["messages"][0]["content"].split()[-1].rstrip("?")

    assert tok1 == tok2 == "<PAN_1>"
    await g.aclose()


@pytest.mark.asyncio
async def test_ephemeral_session_discarded_after_response() -> None:
    g = _guardrail()
    data = _req(f"my PAN is {PAN}")
    await g.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), data, "completion")
    ref = data["metadata"]["maskflow_ref"]
    await g.async_post_call_success_hook(data, UserAPIKeyAuth(), _text_response("done"))
    # ref is gone from the in-process store
    assert ref not in g._inprocess_store._entries  # type: ignore[attr-defined]


def test_supported_event_hooks() -> None:
    from litellm.types.guardrails import GuardrailEventHooks

    hooks = MaskflowGuardrail.get_supported_event_hooks()
    assert set(hooks) == {GuardrailEventHooks.pre_call, GuardrailEventHooks.post_call}


def test_examples_config_builds_the_guardrail() -> None:
    """packages/maskflow-litellm/examples/config.yaml stays loadable through
    the same path litellm's guardrail_registry uses."""
    import pathlib

    import yaml

    cfg_path = pathlib.Path(__file__).parents[1] / "examples" / "config.yaml"
    entry = yaml.safe_load(cfg_path.read_text())["guardrails"][0]
    params = entry["litellm_params"]
    extra = {k: v for k, v in params.items() if k not in ("guardrail", "mode", "default_on")}

    g = MaskflowGuardrail(
        guardrail_name=entry["guardrail_name"],
        event_hook=params["mode"],
        default_on=params["default_on"],
        **extra,
    )
    assert params["guardrail"] == "maskflow_litellm.MaskflowGuardrail"
    assert g._hooks_include_post_call() is True  # type: ignore[attr-defined]


def test_warns_when_post_call_missing(caplog) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        _guardrail(event_hook="pre_call")
    assert "post_call" in caplog.text


@pytest.mark.asyncio
async def test_end_to_end_via_litellm_mock_response() -> None:
    """The guardrail as an actual litellm callback on a mocked completion."""
    g = _guardrail()
    litellm.logging_callback_manager.add_litellm_callback(g)
    try:
        data = _req(f"my PAN is {PAN}")
        await g.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), data, "completion")
        token = data["messages"][0]["content"].split()[-1]

        resp = await litellm.acompletion(
            model="gpt-4o",
            messages=data["messages"],
            mock_response=f"Recorded {token}.",
        )
        await g.async_post_call_success_hook(data, UserAPIKeyAuth(), resp)
        assert resp.choices[0].message.content == f"Recorded {PAN}."
    finally:
        litellm.logging_callback_manager.remove_callback_from_all_lists(g)
