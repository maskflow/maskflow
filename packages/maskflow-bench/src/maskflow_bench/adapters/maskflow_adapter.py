"""Adapter 1: MaskFlow itself, both bundled packs.

Importing maskflow_pack_intl and maskflow_pack_india registers every
recognizer against maskflow-core's global registry as a side effect (same
mechanism bench/indiapii/report.py already relies on for its own,
unrelated L1-L3 accuracy report) -- there is no separate "activate" step.
PIIType values already equal the corpus's own label vocabulary (the corpus
was generated from this pack's own types), so no label translation table
is needed here; labels.py's identity_map() is used by the caller.
"""

from __future__ import annotations

import maskflow_pack_india  # noqa: F401  (import-time registration side effect)
import maskflow_pack_intl  # noqa: F401  (import-time registration side effect)
from maskflow_core.detection import detect


class MaskflowAdapter:
    name = "maskflow"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        spans = detect(text)
        return [(s.start, s.end, str(s.entity_type)) for s in spans]
