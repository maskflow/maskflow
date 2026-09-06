"""MaskflowDeanonymizer: streaming-aware Runnable at the chain tail."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from maskflow_langchain import MaskflowReversibleAnonymizer

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"


def _anon() -> tuple[MaskflowReversibleAnonymizer, str]:
    a = MaskflowReversibleAnonymizer()
    masked = a.anonymize(f"contact {EMAIL}, PAN {PAN}, again {EMAIL}")
    return a, "reply: " + masked


def test_invoke_whole_string() -> None:
    a, masked_reply = _anon()
    assert a.deanonymizer.invoke(masked_reply) == (
        f"reply: contact {EMAIL}, PAN {PAN}, again {EMAIL}"
    )


def test_transform_splits_placeholder_across_chunks() -> None:
    a, masked_reply = _anon()
    for size in (1, 2, 3, 5, 7):
        chunks = [masked_reply[i : i + size] for i in range(0, len(masked_reply), size)]
        out = "".join(a.deanonymizer.transform(iter(chunks)))
        assert out == f"reply: contact {EMAIL}, PAN {PAN}, again {EMAIL}"


def test_stream_method() -> None:
    a, masked_reply = _anon()
    assert "".join(a.deanonymizer.stream(masked_reply)) == (
        f"reply: contact {EMAIL}, PAN {PAN}, again {EMAIL}"
    )


@pytest.mark.asyncio
async def test_atransform() -> None:
    a, masked_reply = _anon()

    async def src():
        for ch in masked_reply:
            yield ch

    out = "".join([piece async for piece in a.deanonymizer.atransform(src())])
    assert out == f"reply: contact {EMAIL}, PAN {PAN}, again {EMAIL}"


def test_reads_mapping_at_call_time() -> None:
    a = MaskflowReversibleAnonymizer()
    d = a.deanonymizer  # created before any anonymize()
    m1 = a.anonymize(f"PAN {PAN}")
    assert d.invoke(m1) == f"PAN {PAN}"


@settings(max_examples=100, deadline=None)
@given(size=st.integers(min_value=1, max_value=40))
def test_arbitrary_chunk_size_round_trips(size: int) -> None:
    a, masked_reply = _anon()
    chunks = [masked_reply[i : i + size] for i in range(0, len(masked_reply), size)]
    assert "".join(a.deanonymizer.transform(iter(chunks))) == (
        f"reply: contact {EMAIL}, PAN {PAN}, again {EMAIL}"
    )


def test_lcel_chain_pipe() -> None:
    from langchain_core.runnables import RunnableLambda

    a = MaskflowReversibleAnonymizer()
    # emulate: anonymize -> "LLM echoes the masked text" -> deanonymize
    chain = (
        RunnableLambda(lambda x: a.anonymize(x["q"]))
        | RunnableLambda(lambda masked: f"The value is {masked}.")
        | a.deanonymizer
    )
    assert chain.invoke({"q": f"is PAN {PAN} ok"}) == f"The value is is PAN {PAN} ok."
    streamed = "".join(chain.stream({"q": f"mail {EMAIL}"}))
    assert streamed == f"The value is mail {EMAIL}."
