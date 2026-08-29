"""Constructs every adapter this harness knows about. Construction itself
must never require the adapter's optional dependency or API key -- that's
what available() (checked lazily by runner.py) is for -- so this module
only imports adapter *modules* (cheap, dependency-free), not the heavy
third-party packages each adapter wraps.
"""

from __future__ import annotations

from ..labels import (
    MASK_PRIVACY_LABEL_MAP,
    NAIVE_REGEX_LABEL_MAP,
    PRESIDIO_CUSTOM_LABEL_MAP,
    PRESIDIO_LABEL_MAP,
    identity_map,
)
from .base import Adapter
from .llm_adapter import LlmAdapter
from .mask_privacy_adapter import MaskPrivacyAdapter
from .maskflow_adapter import MaskflowAdapter
from .naive_regex_adapter import NaiveRegexAdapter
from .presidio_adapter import PresidioAdapter
from .presidio_custom_adapter import PresidioCustomAdapter

# adapter instance, label_map -- the pair runner.py needs for each entry.
# maskflow's label_map is identity_map(canonical_labels), built once
# canonical_labels is known (see build_adapters()).
AdapterEntry = tuple[Adapter, dict[str, str]]


def build_adapters(canonical_labels: tuple[str, ...]) -> list[AdapterEntry]:
    return [
        (MaskflowAdapter(), identity_map(canonical_labels)),
        (PresidioAdapter(), PRESIDIO_LABEL_MAP),
        (PresidioCustomAdapter(), PRESIDIO_CUSTOM_LABEL_MAP),
        (MaskPrivacyAdapter(), MASK_PRIVACY_LABEL_MAP),
        (NaiveRegexAdapter(), NAIVE_REGEX_LABEL_MAP),
        (LlmAdapter(canonical_labels), identity_map(canonical_labels)),
    ]


__all__ = ["Adapter", "AdapterEntry", "build_adapters"]
