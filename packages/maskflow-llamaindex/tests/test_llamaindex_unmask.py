"""unmask_response / collect_node_mapping / response_unmasker."""

from __future__ import annotations

import pytest

pytest.importorskip("llama_index.core")

from llama_index.core.schema import NodeWithScore, TextNode  # noqa: E402
from maskflow_llamaindex import (  # noqa: E402
    MaskflowNodePostprocessor,
    collect_node_mapping,
    response_unmasker,
    unmask_response,
)

pytestmark = pytest.mark.llamaindex

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"


def _masked_source_nodes() -> list[NodeWithScore]:
    raw = [
        NodeWithScore(node=TextNode(text=f"Ramesh's PAN is {PAN}."), score=1.0),
        NodeWithScore(node=TextNode(text=f"Reach Ramesh at {EMAIL}."), score=0.9),
    ]
    return MaskflowNodePostprocessor().postprocess_nodes(raw)


def test_collect_merges_all_node_maps() -> None:
    m = collect_node_mapping(_masked_source_nodes())
    assert m == {"<PERSON_NAME_1>": "Ramesh", "<PAN_1>": PAN, "<EMAIL_1>": EMAIL}


def test_unmask_response_restores_answer() -> None:
    nodes = _masked_source_nodes()
    synthesized = "Per the context, <PERSON_NAME_1>'s PAN is <PAN_1>."
    assert unmask_response(synthesized, nodes) == f"Per the context, Ramesh's PAN is {PAN}."


def test_unmask_response_no_mapping_is_identity() -> None:
    plain = [NodeWithScore(node=TextNode(text="nothing here"), score=1.0)]
    assert unmask_response("an answer", plain) == "an answer"


def test_streaming_response_unmasker_stitches_split_placeholder() -> None:
    nodes = _masked_source_nodes()
    full = "PAN: <PAN_1> and email <EMAIL_1>"
    u = response_unmasker(nodes)
    out = "".join(u.feed(full[i : i + 3]) for i in range(0, len(full), 3)) + u.flush()
    assert out == f"PAN: {PAN} and email {EMAIL}"


def test_collect_accepts_bare_nodes_and_nodewithscore() -> None:
    nws = _masked_source_nodes()
    bare = [n.node for n in nws]
    assert collect_node_mapping(bare) == collect_node_mapping(nws)
