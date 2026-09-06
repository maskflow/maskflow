"""MaskflowNodePostprocessor against real llama-index-core node types."""

from __future__ import annotations

import pytest

pytest.importorskip("llama_index.core")

from llama_index.core.postprocessor.types import BaseNodePostprocessor  # noqa: E402
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode  # noqa: E402
from maskflow_llamaindex import MaskflowNodePostprocessor  # noqa: E402

pytestmark = pytest.mark.llamaindex

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"


def _nodes(*texts: str) -> list[NodeWithScore]:
    return [NodeWithScore(node=TextNode(text=t), score=1.0 - i * 0.1) for i, t in enumerate(texts)]


def test_is_a_node_postprocessor() -> None:
    assert isinstance(MaskflowNodePostprocessor(), BaseNodePostprocessor)
    assert MaskflowNodePostprocessor.class_name() == "MaskflowNodePostprocessor"


def test_masks_text_and_stores_pii_node_info() -> None:
    pp = MaskflowNodePostprocessor()
    [out] = pp.postprocess_nodes(_nodes(f"Contact Ramesh at {EMAIL}, PAN {PAN}"))
    assert EMAIL not in out.node.text and PAN not in out.node.text
    info = out.node.metadata["__pii_node_info__"]
    assert info["<EMAIL_1>"] == EMAIL and info["<PAN_1>"] == PAN
    assert "__pii_node_info__" in out.node.excluded_embed_metadata_keys
    assert "__pii_node_info__" in out.node.excluded_llm_metadata_keys


def test_original_nodes_untouched() -> None:
    nodes = _nodes(f"PAN {PAN}")
    pp = MaskflowNodePostprocessor()
    pp.postprocess_nodes(nodes)
    assert nodes[0].node.text == f"PAN {PAN}"  # deepcopy, not in place


def test_consistent_across_nodes() -> None:
    pp = MaskflowNodePostprocessor(consistent_across_nodes=True)
    out = pp.postprocess_nodes(_nodes(f"Ramesh, PAN {PAN}", f"Ramesh again, mail {EMAIL}"))
    assert "<PERSON_NAME_1>" in out[0].node.text
    assert "<PERSON_NAME_1>" in out[1].node.text  # same token, same person


def test_independent_per_node_when_disabled() -> None:
    pp = MaskflowNodePostprocessor(consistent_across_nodes=False)
    out = pp.postprocess_nodes(_nodes("Ramesh here", "Suresh there"))
    # each node numbered from 1 independently
    assert "<PERSON_NAME_1>" in out[0].node.text
    assert "<PERSON_NAME_1>" in out[1].node.text
    assert out[0].node.metadata["__pii_node_info__"]["<PERSON_NAME_1>"] == "Ramesh"
    assert out[1].node.metadata["__pii_node_info__"]["<PERSON_NAME_1>"] == "Suresh"


def test_mask_query_uses_the_shared_session() -> None:
    pp = MaskflowNodePostprocessor(mask_query=True)
    qb = QueryBundle(query_str=f"what about PAN {PAN}?")
    out = pp.postprocess_nodes(_nodes(f"the record for PAN {PAN}"), query_bundle=qb)
    assert PAN not in qb.query_str
    assert "<PAN_1>" in qb.query_str
    assert "<PAN_1>" in out[0].node.text  # query and node share the token


def test_redact_strategy() -> None:
    pp = MaskflowNodePostprocessor(strategy="redact")
    [out] = pp.postprocess_nodes(_nodes(f"PAN {PAN}"))
    assert out.node.text == "PAN [REDACTED_PAN]"
    assert out.node.metadata["__pii_node_info__"] == {}


def test_node_info_holds_only_that_nodes_placeholders() -> None:
    pp = MaskflowNodePostprocessor()
    out = pp.postprocess_nodes(_nodes(f"PAN {PAN}", f"mail {EMAIL}"))
    assert set(out[0].node.metadata["__pii_node_info__"]) == {"<PAN_1>"}
    assert set(out[1].node.metadata["__pii_node_info__"]) == {"<EMAIL_1>"}


@pytest.mark.asyncio
async def test_async_postprocess() -> None:
    pp = MaskflowNodePostprocessor()
    out = await pp.apostprocess_nodes(_nodes(f"PAN {PAN}"))
    assert "<PAN_1>" in out[0].node.text
