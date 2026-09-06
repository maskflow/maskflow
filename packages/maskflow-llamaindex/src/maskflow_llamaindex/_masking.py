"""Text masking primitives, free of any ``llama_index`` import.

``mask_pii`` returns ``(masked_text, mapping)`` where ``mapping`` is
``{placeholder: original}`` for the reversible strategies (``replace`` /
``surrogate``) and ``{}`` for the non-reversible ones (``redact`` / ``mask``
/ ``hash``) -- matching the shape LlamaIndex's ``PIINodePostprocessor``
stashes in ``node.metadata["__pii_node_info__"]``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import maskflow
from maskflow import RootConfig, Session
from maskflow_core import PIIType
from maskflow_core.config import EntityConfig, MaskflowSection
from maskflow_core.strategies import Strategy

Strategyish = Literal["replace", "surrogate", "redact", "mask", "hash"]

_REVERSIBLE = {Strategy.REPLACE, Strategy.SURROGATE}

# Same metadata key LlamaIndex's PIINodePostprocessor uses, so existing
# unmask code keeps working after the swap.
PII_NODE_INFO_KEY = "__pii_node_info__"


def build_config(
    *,
    strategy: Strategyish = "replace",
    entities: Iterable[str] | None = None,
) -> RootConfig:
    """A ``RootConfig`` with a global strategy and, when ``entities`` is
    given, every other registered ``PIIType`` disabled."""
    try:
        strat = Strategy(strategy)
    except ValueError:
        raise ValueError(
            f"strategy={strategy!r}: expected one of {[s.value for s in Strategy]}"
        ) from None

    entity_config: dict[str, EntityConfig] = {}
    if entities is not None:
        keep = set(entities)
        for known in PIIType.values():
            if known.value not in keep:
                entity_config[known.value] = EntityConfig(enabled=False)

    return RootConfig(
        maskflow=MaskflowSection(default_strategy=strat),
        entities=entity_config,
    )


def new_session(
    *,
    strategy: Strategyish = "replace",
    min_confidence: float | None = None,
    patterns_only: bool = False,
    entities: Iterable[str] | None = None,
) -> Session:
    kwargs: dict[str, object] = {
        "ttl_seconds": None,
        "config": build_config(strategy=strategy, entities=entities),
        "patterns_only": patterns_only,
    }
    if min_confidence is not None:
        kwargs["min_confidence"] = min_confidence
    return maskflow.Session(**kwargs)  # type: ignore[arg-type]


def session_mapping(session: Session, *, present_in: str | None = None) -> dict[str, str]:
    """``{placeholder: original}`` for the reversible entries only. With
    ``present_in`` set, keep only placeholders that appear in that text
    (so a node's stored map holds only what that node needs)."""
    mapping = session.mapping
    return {
        token: mapping[token].original
        for token in mapping
        if mapping[token].reversible and (present_in is None or token in present_in)
    }


def mask_pii(
    text: str,
    *,
    strategy: Strategyish = "replace",
    min_confidence: float | None = None,
    patterns_only: bool = False,
) -> tuple[str, dict[str, str]]:
    """Mask ``text`` in a throwaway session; return ``(masked, mapping)``."""
    with new_session(
        strategy=strategy, min_confidence=min_confidence, patterns_only=patterns_only
    ) as session:
        masked = session.mask(text)
        return masked, session_mapping(session, present_in=masked)


__all__ = [
    "Strategyish",
    "PII_NODE_INFO_KEY",
    "build_config",
    "new_session",
    "session_mapping",
    "mask_pii",
    "_REVERSIBLE",
]
