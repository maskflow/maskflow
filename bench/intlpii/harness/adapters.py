"""Constructs every adapter the intl harness runs. Four of the five are
bench.indiapii.harness's own adapter classes, reused unchanged -- they
were written corpus-agnostic (they emit raw (start, end, label) spans in
their own vocabulary; translation to canonical labels is labels.py's job,
not theirs). Only the naive-regex baseline is intl-specific.

Construction never requires an adapter's optional dependency or API key --
that is what available() (checked lazily by runner.py) is for.
"""

from __future__ import annotations

from maskflow_bench.adapters import Adapter
from maskflow_bench.adapters.maskflow_adapter import MaskflowAdapter

from bench.indiapii.harness.adapters.llm_adapter import LlmAdapter
from bench.indiapii.harness.adapters.presidio_adapter import PresidioAdapter

from .labels import (
    MASK_PRIVACY_LABEL_MAP,
    NAIVE_REGEX_LABEL_MAP,
    PRESIDIO_LABEL_MAP,
    identity_map,
)
from .mask_privacy_intl import MaskPrivacyIntlAdapter
from .naive_regex import NaiveRegexIntlAdapter

AdapterEntry = tuple[Adapter, dict[str, str]]


def build_adapters(canonical_labels: tuple[str, ...]) -> list[AdapterEntry]:
    return [
        (MaskflowAdapter(), identity_map(canonical_labels)),
        (PresidioAdapter(), PRESIDIO_LABEL_MAP),
        (MaskPrivacyIntlAdapter(), MASK_PRIVACY_LABEL_MAP),
        (NaiveRegexIntlAdapter(), NAIVE_REGEX_LABEL_MAP),
        (LlmAdapter(canonical_labels), identity_map(canonical_labels)),
    ]


__all__ = ["Adapter", "AdapterEntry", "build_adapters"]
