"""``MaskflowQueryEngine`` -- wraps a query engine that already has
``MaskflowNodePostprocessor`` in its ``node_postprocessors`` and restores
originals in the synthesized answer, so callers do not have to remember to
merge the per-node maps by hand.

    from llama_index.core import VectorStoreIndex
    from maskflow_llamaindex import MaskflowNodePostprocessor, MaskflowQueryEngine

    inner = index.as_query_engine(node_postprocessors=[MaskflowNodePostprocessor()])
    engine = MaskflowQueryEngine(inner)

    print(engine.query("What is Ramesh's PAN?"))   # answer has real values restored

This wrapper does not mask the query or inject the postprocessor -- compose
those yourself. It only unmasks the response (string or streamed) using
``response.source_nodes``.
"""

from __future__ import annotations

from typing import Any

from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.base.response.schema import (
    PydanticResponse,
    Response,
    StreamingResponse,
)
from llama_index.core.schema import QueryBundle
from maskflow.streaming import StreamingUnmasker, unmask_whole

from ._masking import PII_NODE_INFO_KEY
from .unmask import collect_node_mapping


class MaskflowQueryEngine(BaseQueryEngine):
    def __init__(
        self, inner: BaseQueryEngine, *, pii_node_info_key: str = PII_NODE_INFO_KEY
    ) -> None:
        super().__init__(callback_manager=getattr(inner, "callback_manager", None))
        self._inner = inner
        self._pii_node_info_key = pii_node_info_key

    # -- PromptMixin plumbing (delegate to the inner engine) --------------
    def _get_prompts(self) -> dict[str, Any]:
        return {}

    def _get_prompt_modules(self) -> dict[str, Any]:
        return {"inner": self._inner}

    def _update_prompts(self, prompts_dict: dict[str, Any]) -> None:
        return None

    # -- unmasking -------------------------------------------------------
    def _restore(self, response: Any) -> Any:
        mapping = collect_node_mapping(
            getattr(response, "source_nodes", []), pii_node_info_key=self._pii_node_info_key
        )
        if not mapping:
            return response
        if isinstance(response, Response) and isinstance(response.response, str):
            response.response = unmask_whole(response.response, mapping)
        elif isinstance(response, PydanticResponse):
            return self._restore(response.get_response())
        elif isinstance(response, StreamingResponse):
            response.response_gen = _unmasked_gen(response.response_gen, mapping)
        return response

    def _query(self, query_bundle: QueryBundle) -> Any:
        return self._restore(self._inner.query(query_bundle))

    async def _aquery(self, query_bundle: QueryBundle) -> Any:
        return self._restore(await self._inner.aquery(query_bundle))


def _unmasked_gen(gen: Any, mapping: dict[str, str]) -> Any:
    u = StreamingUnmasker(mapping)
    for token in gen:
        out = u.feed(token)
        if out:
            yield out
    tail = u.flush()
    if tail:
        yield tail
