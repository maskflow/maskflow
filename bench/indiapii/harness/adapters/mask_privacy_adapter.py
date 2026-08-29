"""Adapter 4: mask-privacy (`pip install mask-privacy`), used entirely at
its own defaults (confidence_threshold=0.7, its own pipeline order) --
never tuned in this adapter's favor, same rule as every other adapter.

Confirmed by inspecting the installed package: `detect_entities_with_confidence()`
is a Presidio-backed two-tier pipeline (a regex/checksum "DLP" tier, then a
Presidio NLP tier). Its DLP registry has zero India-specific entity types
(checked directly against the installed package -- 38 raw types, all
US/EU/generic), so this is expected to look similar to stock Presidio on
this corpus, just under mask-privacy's own label names (see labels.py).

Tier-1 ("dlp_heuristic") entities come back with real start/end offsets;
Tier-2 ("nlp") entities only come back with a matched `value` string, no
offsets (the text has already been rewritten/excised by the time Tier 2
runs) -- those are relocated with offsets.locate_span(), and any that can't
be found verbatim in the original text are dropped and counted, never
silently guessed at.

Needs MASK_DEV_MODE=true (or a real MASK_ENCRYPTION_KEY) to run headless --
set here via os.environ.setdefault so this adapter is self-contained and
doesn't require the harness's caller to know about it.
"""

from __future__ import annotations

import os
from typing import Any

from ..offsets import locate_span

os.environ.setdefault("MASK_DEV_MODE", "true")


class MaskPrivacyAdapter:
    name = "mask_privacy"

    def __init__(self) -> None:
        self._detect_fn: Any = None
        self._unavailable_reason: str | None = None

    def available(self) -> tuple[bool, str]:
        if self._unavailable_reason is not None:
            return False, self._unavailable_reason
        if self._detect_fn is not None:
            return True, ""
        try:
            from mask_privacy import detect_entities_with_confidence

            detect_entities_with_confidence("smoke test, no PII here.")
        except Exception as exc:  # noqa: BLE001
            self._unavailable_reason = f"mask-privacy init failed: {exc}"
            return False, self._unavailable_reason
        self._detect_fn = detect_entities_with_confidence
        return True, ""

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        entities = self._detect_fn(text)
        used_starts: set[int] = set()
        found: list[tuple[int, int, str]] = []
        for e in entities:
            if "start" in e and "end" in e:
                used_starts.add(e["start"])
                found.append((e["start"], e["end"], e["type"]))
        for e in entities:
            if "start" in e and "end" in e:
                continue
            located = locate_span(text, e.get("value", ""), used_starts)
            if located is not None:
                found.append((located[0], located[1], e["type"]))
        return found
