"""``unmask_stream`` correctness over arbitrary chunk boundaries, litellm-free."""

from __future__ import annotations

import maskflow
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from litellm_response_fakes import aiter, delta, stream_choice, stream_chunk
from maskflow_litellm._masking import mask_request_data
from maskflow_litellm._streaming import unmask_stream

PAN = "ABCPE1234F"  # synthetic, structurally valid
EMAIL = "alice@example.com"


async def _collect(session, fragments: list[str]) -> str:
    chunks = [stream_chunk(stream_choice(delta(content=f))) for f in fragments]
    chunks.append(stream_chunk(stream_choice(delta(content=None), finish_reason="stop")))
    out: list[str] = []
    async for chunk in unmask_stream(session, aiter(chunks)):
        c = chunk.choices[0].delta.content
        if isinstance(c, str):
            out.append(c)
    return "".join(out)


def _session_with(text: str):
    session = maskflow.session(config=maskflow.RootConfig())
    data = {"messages": [{"role": "user", "content": text}]}
    mask_request_data(session, data)
    return session, data["messages"][0]["content"]


@pytest.mark.asyncio
async def test_placeholder_split_across_chunks_is_stitched() -> None:
    session, masked = _session_with(f"my email is {EMAIL} and PAN {PAN}")
    # masked looks like "my email is <EMAIL_1> and PAN <PAN_1>"
    for cut in range(1, len(masked)):
        s2, _ = _session_with(f"my email is {EMAIL} and PAN {PAN}")
        got = await _collect(s2, [masked[:cut], masked[cut:]])
        assert got == f"my email is {EMAIL} and PAN {PAN}"


@pytest.mark.asyncio
async def test_char_by_char_stream() -> None:
    session, masked = _session_with(f"reach {EMAIL}")
    got = await _collect(session, list(masked))
    assert got == f"reach {EMAIL}"


@pytest.mark.asyncio
async def test_unknown_token_from_model_left_literal() -> None:
    session, masked = _session_with(f"mail {EMAIL}")
    got = await _collect(session, [masked + " and <EMAIL_9>"])
    assert got == f"mail {EMAIL} and <EMAIL_9>"


@pytest.mark.asyncio
async def test_tool_call_argument_deltas_unmasked() -> None:
    session, masked = _session_with(f"PAN {PAN}")
    token = masked.split()[-1]
    frags = ['{"pan": "', token[:3], token[3:], '"}']

    chunks = []
    for f in frags:
        call = stream_choice(
            delta(
                tool_calls=[
                    type("C", (), {"index": 0, "function": type("F", (), {"arguments": f})()})()
                ]
            )
        )
        chunks.append(stream_chunk(call))
    chunks.append(stream_chunk(stream_choice(delta(content=None), finish_reason="tool_calls")))

    out = []
    async for chunk in unmask_stream(session, aiter(chunks)):
        for ch in chunk.choices:
            for tc in ch.delta.tool_calls or []:
                out.append(tc.function.arguments)
    assert "".join(out) == f'{{"pan": "{PAN}"}}'


@settings(max_examples=150, deadline=None)
@given(splits=st.lists(st.integers(min_value=1, max_value=200)))
@pytest.mark.asyncio
async def test_arbitrary_chunking_round_trips(splits: list[int]) -> None:
    original = f"contact {EMAIL}, PAN {PAN}, again {EMAIL}"
    session, masked = _session_with(original)
    cuts = sorted(p for p in splits if 0 < p < len(masked))
    bounds = [0, *cuts, len(masked)]
    frags = [masked[a:b] for a, b in zip(bounds[:-1], bounds[1:], strict=True)]
    assert await _collect(session, frags) == original
