"""MaskflowIngestionTransform."""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("llama_index.core")

from llama_index.core.schema import TextNode, TransformComponent  # noqa: E402
from maskflow_llamaindex import MaskflowIngestionTransform  # noqa: E402

pytestmark = pytest.mark.llamaindex

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"


def test_is_a_transform_component() -> None:
    assert isinstance(MaskflowIngestionTransform(), TransformComponent)
    assert MaskflowIngestionTransform.class_name() == "MaskflowIngestionTransform"


def test_redact_default_no_mapping_stored() -> None:
    nodes = [TextNode(text=f"PAN {PAN} mail {EMAIL}")]
    out = MaskflowIngestionTransform()(nodes)
    assert out[0].text == "PAN [REDACTED_PAN] mail [REDACTED_EMAIL]"
    assert "__pii_node_info__" not in out[0].metadata


def test_masks_in_place_across_nodes_consistently() -> None:
    nodes = [TextNode(text=f"Ramesh, PAN {PAN}"), TextNode(text="Ramesh again")]
    MaskflowIngestionTransform(strategy="replace")(nodes)
    assert "<PERSON_NAME_1>" in nodes[0].text
    assert "<PERSON_NAME_1>" in nodes[1].text


def test_surrogate_strategy() -> None:
    nodes = [TextNode(text=f"mail {EMAIL}")]
    MaskflowIngestionTransform(strategy="surrogate")(nodes)
    assert EMAIL not in nodes[0].text and "@" in nodes[0].text


def test_store_mapping_reversible_warns_and_stores_per_node() -> None:
    nodes = [TextNode(text=f"PAN {PAN}"), TextNode(text=f"mail {EMAIL}")]
    with pytest.warns(UserWarning, match="vector store"):
        MaskflowIngestionTransform(strategy="replace", store_mapping=True)(nodes)
    assert nodes[0].metadata["__pii_node_info__"] == {"<PAN_1>": PAN}
    assert nodes[1].metadata["__pii_node_info__"] == {"<EMAIL_1>": EMAIL}
    assert "__pii_node_info__" in nodes[0].excluded_embed_metadata_keys


def test_store_mapping_with_redact_does_not_warn() -> None:
    nodes = [TextNode(text=f"PAN {PAN}")]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        MaskflowIngestionTransform(strategy="redact", store_mapping=True)(nodes)
    assert nodes[0].metadata["__pii_node_info__"] == {}  # redact has nothing reversible


@pytest.mark.asyncio
async def test_acall() -> None:
    nodes = [TextNode(text=f"PAN {PAN}")]
    out = await MaskflowIngestionTransform().acall(nodes)
    assert out[0].text == "PAN [REDACTED_PAN]"
