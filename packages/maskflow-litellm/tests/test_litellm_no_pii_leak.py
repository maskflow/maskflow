"""MaskFlow release rule #1: raw PII never reaches logs, error text, repr,
or request metadata. These guard the LiteLLM adapter's own surfaces."""

from __future__ import annotations

import json
import logging

import maskflow
import pytest
from litellm_response_fakes import aiter, delta, stream_choice, stream_chunk
from maskflow_litellm._masking import mask_request_data
from maskflow_litellm._streaming import unmask_stream

PAN = "ABCPE1234F"  # synthetic
EMAIL = "alice@example.com"
MOBILE = "9812345678"
SECRETS = (PAN, EMAIL, MOBILE)


def _assert_clean(blob: str) -> None:
    for secret in SECRETS:
        assert secret not in blob


@pytest.mark.leak
def test_masked_request_and_metadata_carry_no_originals() -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    data = {
        "messages": [{"role": "user", "content": f"PAN {PAN}, mail {EMAIL}, mobile {MOBILE}"}],
        "metadata": {"maskflow_ref": "c:call-123"},
    }
    mask_request_data(session, data)
    _assert_clean(json.dumps(data))


@pytest.mark.leak
def test_session_object_repr_has_no_pii() -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    session.mask(f"PAN {PAN}, mail {EMAIL}")
    _assert_clean(repr(session))
    _assert_clean(repr(session.mapping))


@pytest.mark.leak
@pytest.mark.asyncio
async def test_streaming_debug_logging_has_no_pii(caplog: pytest.LogCaptureFixture) -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    data = {"messages": [{"role": "user", "content": f"mail {EMAIL}"}]}
    mask_request_data(session, data)
    masked = data["messages"][0]["content"]

    chunks = [stream_chunk(stream_choice(delta(content=masked)))]
    chunks.append(stream_chunk(stream_choice(delta(content=None), finish_reason="stop")))

    with caplog.at_level(logging.DEBUG):
        async for _ in unmask_stream(session, aiter(chunks)):
            pass
    _assert_clean(caplog.text)
