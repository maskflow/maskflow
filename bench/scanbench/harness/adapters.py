"""Adapters for the scan-log harness.

Two MaskFlow columns, matching the two passes `maskflow scan` runs:
- `maskflow_deep`   -> `detect()`               (what `--deep` runs)
- `maskflow_patterns` -> `detect_patterns_only()` (the default fast pass over the full corpus)

`scan/worker.py`'s `scan_with()` calls exactly these functions; with the
default config its extra kwargs (per-entity thresholds, disabled types,
exclusions) are empty, so calling them directly here is faithful.

Presidio (`presidio_oob`) and a naive log regex are the baselines.
"""

from __future__ import annotations

from bench.indiapii.harness.adapters.base import Adapter
from bench.indiapii.harness.adapters.presidio_adapter import PresidioAdapter

from .labels import NAIVE_REGEX_LABEL_MAP, PRESIDIO_LABEL_MAP, identity_map
from .naive_regex import NaiveLogRegexAdapter

AdapterEntry = tuple[Adapter, dict[str, str]]


class _MaskflowBase:
    def available(self) -> tuple[bool, str]:
        return True, ""

    def _spans(self, text: str) -> list[tuple[int, int, str]]:  # pragma: no cover - overridden
        raise NotImplementedError


class MaskflowDeepAdapter(_MaskflowBase):
    name = "maskflow_deep"

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        import maskflow_pack_india  # noqa: F401
        import maskflow_pack_intl  # noqa: F401
        from maskflow_core.detection import detect

        return [(s.start, s.end, str(s.entity_type)) for s in detect(text)]


class MaskflowPatternsAdapter(_MaskflowBase):
    name = "maskflow_patterns"

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        import maskflow_pack_india  # noqa: F401
        import maskflow_pack_intl  # noqa: F401
        from maskflow_core.detection import detect_patterns_only

        return [(s.start, s.end, str(s.entity_type)) for s in detect_patterns_only(text)]


def build_adapters(canonical_labels: tuple[str, ...]) -> list[AdapterEntry]:
    return [
        (MaskflowDeepAdapter(), identity_map(canonical_labels)),
        (MaskflowPatternsAdapter(), identity_map(canonical_labels)),
        (PresidioAdapter(), PRESIDIO_LABEL_MAP),
        (NaiveLogRegexAdapter(), NAIVE_REGEX_LABEL_MAP),
    ]


__all__ = [
    "AdapterEntry",
    "MaskflowDeepAdapter",
    "MaskflowPatternsAdapter",
    "build_adapters",
]
