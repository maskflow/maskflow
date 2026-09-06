"""``MaskflowNodePostprocessor`` -- a drop-in for
``llama_index.core.postprocessor.PIINodePostprocessor`` that masks PII in
retrieved nodes before they reach the response synthesizer.

``PIINodePostprocessor`` needs an LLM and ``NERPIINodePostprocessor`` needs
a HuggingFace pipeline; this one runs MaskFlow's local detection engine, so
it is fast, offline, and covers the Indian identifiers (Aadhaar, PAN,
GSTIN, UPI, IFSC, ABHA, Indian names / addresses) alongside the generic
PII. The output shape is identical: each node's text is masked, the
``{placeholder: original}`` map goes into ``node.metadata["__pii_node_info__"]``
(same key, same metadata exclusions), so existing code that unmasks a
response by merging those maps keeps working.

    from llama_index.core.query_engine import RetrieverQueryEngine
    from maskflow_llamaindex import MaskflowNodePostprocessor

    engine = RetrieverQueryEngine.from_args(
        retriever, node_postprocessors=[MaskflowNodePostprocessor()]
    )

By default one MaskFlow session is shared across every node in a call (and
the query), so ``<PERSON_NAME_1>`` is the same person wherever it appears --
``PIINodePostprocessor`` numbers each node independently. Restore the
answer with ``maskflow_llamaindex.unmask_response(answer, response.source_nodes)``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from llama_index.core.bridge.pydantic import Field
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import MetadataMode, NodeWithScore, QueryBundle

from ._masking import PII_NODE_INFO_KEY, Strategyish, new_session, session_mapping

if TYPE_CHECKING:
    from maskflow import Session


class MaskflowNodePostprocessor(BaseNodePostprocessor):
    """Mask PII in retrieved node text with MaskFlow."""

    pii_node_info_key: str = PII_NODE_INFO_KEY
    strategy: Strategyish = "replace"
    min_confidence: float | None = None
    patterns_only: bool = False
    consistent_across_nodes: bool = True
    mask_query: bool = False
    metadata_mode: MetadataMode = Field(default=MetadataMode.LLM)

    @classmethod
    def class_name(cls) -> str:
        return "MaskflowNodePostprocessor"

    def _session(self) -> Session:
        return new_session(
            strategy=self.strategy,
            min_confidence=self.min_confidence,
            patterns_only=self.patterns_only,
        )

    def mask_pii(self, text: str, session: Session | None = None) -> tuple[str, dict[str, str]]:
        """Mask PII in ``text``; return ``(masked, {placeholder: original})``
        where the map holds only the placeholders present in ``text``. Pass
        ``session`` to keep placeholder identity across calls."""
        if session is not None:
            masked = session.mask(text)
            return masked, session_mapping(session, present_in=masked)
        with self._session() as own:
            masked = own.mask(text)
            return masked, session_mapping(own, present_in=masked)

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: QueryBundle | None = None,
    ) -> list[NodeWithScore]:
        shared = self._session() if self.consistent_across_nodes else None
        try:
            if shared is not None and self.mask_query and query_bundle is not None:
                query_bundle.query_str = shared.mask(query_bundle.query_str)
                query_bundle.custom_embedding_strs = None

            new_nodes: list[NodeWithScore] = []
            for node_with_score in nodes:
                node = node_with_score.node
                new_text, mapping = self.mask_pii(
                    node.get_content(metadata_mode=self.metadata_mode), shared
                )
                new_node = deepcopy(node)
                if self.pii_node_info_key not in new_node.excluded_embed_metadata_keys:
                    new_node.excluded_embed_metadata_keys.append(self.pii_node_info_key)
                if self.pii_node_info_key not in new_node.excluded_llm_metadata_keys:
                    new_node.excluded_llm_metadata_keys.append(self.pii_node_info_key)
                existing = new_node.metadata.get(self.pii_node_info_key, {})
                new_node.metadata[self.pii_node_info_key] = {**existing, **mapping}
                new_node.set_content(new_text)
                new_nodes.append(NodeWithScore(node=new_node, score=node_with_score.score))
            return new_nodes
        finally:
            if shared is not None:
                shared.close()
