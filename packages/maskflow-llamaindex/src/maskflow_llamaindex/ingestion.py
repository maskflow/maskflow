"""``MaskflowIngestionTransform`` -- a ``TransformComponent`` that masks PII
in node text at ingestion time, so raw PII is never embedded or written to
the vector store.

    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from maskflow_llamaindex import MaskflowIngestionTransform

    pipeline = IngestionPipeline(
        transformations=[
            SentenceSplitter(),
            MaskflowIngestionTransform(),   # PII gone before the next step
            embed_model,
        ]
    )

The default strategy is ``redact`` (``[REDACTED_PAN]``), which is **not
reversible**: there is no mapping, so nothing sensitive is stored. That is
the point of masking at ingestion. ``store_mapping=True`` writes the
reverse map into each node's metadata, which then lands in the vector store
-- only do that if that store is itself trusted, and it warns.

For a reversible flow, prefer masking at *query* time with
``MaskflowNodePostprocessor`` instead, whose mapping lives only for the
query.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import Any

from llama_index.core.schema import BaseNode, TransformComponent

from ._masking import (
    _REVERSIBLE,
    PII_NODE_INFO_KEY,
    Strategyish,
    new_session,
    session_mapping,
)


class MaskflowIngestionTransform(TransformComponent):
    """Mask PII in node text during ingestion."""

    strategy: Strategyish = "redact"
    min_confidence: float | None = None
    patterns_only: bool = False
    store_mapping: bool = False
    pii_node_info_key: str = PII_NODE_INFO_KEY

    @classmethod
    def class_name(cls) -> str:
        return "MaskflowIngestionTransform"

    def _check(self) -> None:
        from maskflow_core.strategies import Strategy

        if self.store_mapping and Strategy(self.strategy) in _REVERSIBLE:
            warnings.warn(
                "MaskflowIngestionTransform(store_mapping=True): the reverse map is "
                "written to node metadata and will be persisted in your vector store. "
                "Raw PII then lives in that store. Only do this if the store is trusted.",
                stacklevel=3,
            )

    def __call__(self, nodes: Sequence[BaseNode], **kwargs: Any) -> Sequence[BaseNode]:
        self._check()
        with new_session(
            strategy=self.strategy,
            min_confidence=self.min_confidence,
            patterns_only=self.patterns_only,
        ) as session:
            for node in nodes:
                masked = session.mask(node.get_content())
                node.set_content(masked)
                if self.store_mapping:
                    if self.pii_node_info_key not in node.excluded_embed_metadata_keys:
                        node.excluded_embed_metadata_keys.append(self.pii_node_info_key)
                    if self.pii_node_info_key not in node.excluded_llm_metadata_keys:
                        node.excluded_llm_metadata_keys.append(self.pii_node_info_key)
                    node.metadata[self.pii_node_info_key] = session_mapping(
                        session, present_in=masked
                    )
        return nodes
