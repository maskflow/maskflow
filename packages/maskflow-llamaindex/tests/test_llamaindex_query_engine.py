"""MaskflowQueryEngine wraps an inner engine and unmasks the answer."""

from __future__ import annotations

import pytest

pytest.importorskip("llama_index.core")

from llama_index.core.base.base_query_engine import BaseQueryEngine  # noqa: E402
from llama_index.core.base.response.schema import Response, StreamingResponse  # noqa: E402
from llama_index.core.schema import NodeWithScore, TextNode  # noqa: E402
from maskflow_llamaindex import MaskflowNodePostprocessor, MaskflowQueryEngine  # noqa: E402

pytestmark = pytest.mark.llamaindex

PAN = "ABCPE1234F"


def _source_nodes():
    raw = [NodeWithScore(node=TextNode(text=f"Ramesh's PAN is {PAN}."), score=1.0)]
    return MaskflowNodePostprocessor().postprocess_nodes(raw)


class _FakeInner(BaseQueryEngine):
    def __init__(self, response):
        super().__init__(callback_manager=None)
        self._response = response

    def _get_prompts(self):
        return {}

    def _get_prompt_modules(self):
        return {}

    def _update_prompts(self, prompts):
        return None

    def _query(self, query_bundle):
        return self._response

    async def _aquery(self, query_bundle):
        return self._response


def test_unmasks_plain_response() -> None:
    resp = Response(response="<PERSON_NAME_1> has PAN <PAN_1>.", source_nodes=_source_nodes())
    out = MaskflowQueryEngine(_FakeInner(resp)).query("what is the PAN")
    assert str(out) == f"Ramesh has PAN {PAN}."


@pytest.mark.asyncio
async def test_unmasks_via_aquery() -> None:
    inner = _FakeInner(Response(response="PAN <PAN_1>.", source_nodes=_source_nodes()))
    out = await MaskflowQueryEngine(inner).aquery("x")
    assert str(out) == f"PAN {PAN}."


def test_unmasks_streaming_response() -> None:
    def gen():
        yield from ["PAN is <PA", "N_1> ok"]

    inner = _FakeInner(StreamingResponse(response_gen=gen(), source_nodes=_source_nodes()))
    out = MaskflowQueryEngine(inner).query("x")
    assert "".join(out.response_gen) == f"PAN is {PAN} ok"


def test_no_mapping_passes_response_through() -> None:
    inner = _FakeInner(Response(response="nothing masked", source_nodes=[]))
    assert str(MaskflowQueryEngine(inner).query("x")) == "nothing masked"
