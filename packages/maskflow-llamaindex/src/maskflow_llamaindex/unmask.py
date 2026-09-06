"""Restore originals in a synthesized answer, using the per-node maps that
``MaskflowNodePostprocessor`` left in ``node.metadata["__pii_node_info__"]``.

    response = query_engine.query("...")
    answer = maskflow_llamaindex.unmask_response(str(response), response.source_nodes)

For a streamed answer, feed chunks through ``StreamingUnmasker`` built from
``collect_node_mapping(response.source_nodes)`` so a placeholder split
across chunks is stitched.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from maskflow.streaming import StreamingUnmasker, unmask_whole

from ._masking import PII_NODE_INFO_KEY


def _node_of(item: Any) -> Any:
    # accepts a NodeWithScore, a BaseNode, or anything with .metadata
    return getattr(item, "node", item)


def collect_node_mapping(
    source_nodes: Iterable[Any],
    *,
    pii_node_info_key: str = PII_NODE_INFO_KEY,
) -> dict[str, str]:
    """Merge every node's ``__pii_node_info__`` into one
    ``{placeholder: original}`` dict."""
    merged: dict[str, str] = {}
    for item in source_nodes or []:
        node = _node_of(item)
        info = getattr(node, "metadata", {}).get(pii_node_info_key)
        if isinstance(info, dict):
            for placeholder, original in info.items():
                merged.setdefault(str(placeholder), str(original))
    return merged


def unmask_response(
    text: str,
    source_nodes: Iterable[Any],
    *,
    pii_node_info_key: str = PII_NODE_INFO_KEY,
) -> str:
    """Restore originals in ``text`` from the source nodes' stored maps."""
    mapping = collect_node_mapping(source_nodes, pii_node_info_key=pii_node_info_key)
    if not mapping:
        return text
    return unmask_whole(text, mapping)


def response_unmasker(
    source_nodes: Iterable[Any],
    *,
    pii_node_info_key: str = PII_NODE_INFO_KEY,
) -> StreamingUnmasker:
    """A ``StreamingUnmasker`` for a streamed answer -- ``feed(chunk)`` per
    delta, ``flush()`` at the end."""
    return StreamingUnmasker(
        collect_node_mapping(source_nodes, pii_node_info_key=pii_node_info_key)
    )
