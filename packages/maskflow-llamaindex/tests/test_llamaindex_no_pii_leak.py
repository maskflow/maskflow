"""MaskFlow release rule #1: raw PII never reaches logs, repr, or node
metadata / text that leaves the process (embeddings, vector store)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("llama_index.core")

from llama_index.core.schema import NodeWithScore, TextNode  # noqa: E402
from maskflow_llamaindex import (  # noqa: E402
    MaskflowIngestionTransform,
    MaskflowNodePostprocessor,
    mask_pii,
)

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"
MOBILE = "9812345678"
SECRETS = (PAN, EMAIL, MOBILE)


def _clean(blob: str) -> None:
    for s in SECRETS:
        assert s not in blob


@pytest.mark.leak
def test_ingestion_redact_leaves_no_pii_anywhere_on_the_node() -> None:
    nodes = [TextNode(text=f"PAN {PAN}, mail {EMAIL}, mobile {MOBILE}")]
    MaskflowIngestionTransform()(nodes)  # default redact
    # text, metadata, and the whole serialized node
    _clean(nodes[0].get_content())
    _clean(json.dumps(nodes[0].metadata))
    _clean(nodes[0].to_json())


@pytest.mark.leak
def test_postprocessed_node_text_and_embed_metadata_have_no_pii() -> None:
    raw = [NodeWithScore(node=TextNode(text=f"PAN {PAN} mail {EMAIL}"), score=1.0)]
    [out] = MaskflowNodePostprocessor().postprocess_nodes(raw)
    from llama_index.core.schema import MetadataMode

    # what the embedding model and the LLM actually see excludes __pii_node_info__
    _clean(out.node.get_content(metadata_mode=MetadataMode.EMBED))
    _clean(out.node.get_content(metadata_mode=MetadataMode.LLM))


@pytest.mark.leak
def test_mask_pii_repr_and_masked_text_have_no_pii() -> None:
    masked, mapping = mask_pii(f"PAN {PAN} mail {EMAIL} mobile {MOBILE}")
    _clean(masked)
    # the mapping *values* are the originals by design; the keys are not
    for placeholder in mapping:
        _clean(placeholder)


@pytest.mark.leak
def test_postprocessor_repr_has_no_pii() -> None:
    pp = MaskflowNodePostprocessor()
    pp.postprocess_nodes([NodeWithScore(node=TextNode(text=f"PAN {PAN}"), score=1.0)])
    _clean(repr(pp))
