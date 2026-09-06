"""MaskFlow for LlamaIndex.

Three pieces:

* ``MaskflowNodePostprocessor`` -- a drop-in for
  ``llama_index.core.postprocessor.PIINodePostprocessor`` that masks PII in
  retrieved nodes before the response synthesizer, with no LLM or HF model.
* ``MaskflowIngestionTransform`` -- a ``TransformComponent`` that masks PII
  at ingestion, so raw PII is never embedded or stored.
* ``unmask_response`` / ``MaskflowQueryEngine`` -- restore originals in the
  synthesized answer from the per-node maps.

``MaskflowNodePostprocessor`` and ``MaskflowIngestionTransform`` need
``llama-index-core``; ``mask_pii`` (in ``maskflow_llamaindex._masking``)
does not. The submodules are imported lazily so importing this package does
not require ``llama-index-core``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._masking import PII_NODE_INFO_KEY, mask_pii

__all__ = [
    "MaskflowNodePostprocessor",
    "MaskflowIngestionTransform",
    "MaskflowQueryEngine",
    "unmask_response",
    "collect_node_mapping",
    "response_unmasker",
    "mask_pii",
    "PII_NODE_INFO_KEY",
]

if TYPE_CHECKING:
    from .ingestion import MaskflowIngestionTransform
    from .postprocessor import MaskflowNodePostprocessor
    from .query_engine import MaskflowQueryEngine
    from .unmask import collect_node_mapping, response_unmasker, unmask_response

_LAZY = {
    "MaskflowNodePostprocessor": ("postprocessor", "MaskflowNodePostprocessor"),
    "MaskflowIngestionTransform": ("ingestion", "MaskflowIngestionTransform"),
    "MaskflowQueryEngine": ("query_engine", "MaskflowQueryEngine"),
    "unmask_response": ("unmask", "unmask_response"),
    "collect_node_mapping": ("unmask", "collect_node_mapping"),
    "response_unmasker": ("unmask", "response_unmasker"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(f".{target[0]}", __name__)
    return getattr(module, target[1])
