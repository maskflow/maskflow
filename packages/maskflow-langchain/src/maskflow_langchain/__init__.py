"""MaskFlow for LangChain.

A reversible PII anonymizer / deanonymizer pair that drops in for
``langchain_experimental.data_anonymizer``'s Presidio anonymizer (Indian
identifiers included), plus a leak-guard callback.

    from maskflow_langchain import MaskflowReversibleAnonymizer

    anonymizer = MaskflowReversibleAnonymizer()
    chain = (
        {"question": lambda x: anonymizer.anonymize(x["question"])}
        | prompt
        | llm
        | StrOutputParser()
        | anonymizer.deanonymizer     # streaming-aware Runnable
    )
"""

from __future__ import annotations

from .anonymizer import MaskflowAnonymizer, MaskflowReversibleAnonymizer
from .base import AnonymizerBase, ReversibleAnonymizerBase
from .callbacks import (
    AsyncMaskflowLeakGuardCallback,
    MaskflowLeakGuardCallback,
    MaskflowPIILeakError,
)
from .matching import (
    MappingDataType,
    case_insensitive_matching_strategy,
    exact_matching_strategy,
)
from .runnables import MaskflowDeanonymizer

__all__ = [
    "MaskflowAnonymizer",
    "MaskflowReversibleAnonymizer",
    "MaskflowDeanonymizer",
    "MaskflowLeakGuardCallback",
    "AsyncMaskflowLeakGuardCallback",
    "MaskflowPIILeakError",
    "AnonymizerBase",
    "ReversibleAnonymizerBase",
    "MappingDataType",
    "exact_matching_strategy",
    "case_insensitive_matching_strategy",
]
