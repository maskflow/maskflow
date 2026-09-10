"""mask-privacy adapter for the intl corpus.

Differs from bench.indiapii.harness.adapters.mask_privacy_adapter in one
way: it calls the scanner's `scan_and_return_entities(text,
encode_fn=<no-op>)` directly instead of the `detect_entities_with_confidence`
convenience wrapper. The wrapper always runs mask-privacy's stateful
format-preserving-encryption vault to produce a `masked_value` for every
hit; over a 1800-document run that vault fills and starts raising
`TokenCollisionError` on the synthetic `+1-555-01xx` phone numbers (~980 of
1800 docs failed this way with the wrapper). The benchmark scores
`start/end/type` only and never looks at `masked_value`, so disabling the
tokenizer with a no-op `encode_fn` is a faithful detection-only measurement,
not a tuning in mask-privacy's favor -- it is still run at its default
pipeline (`dlp, regex, checksum, nlp`) and default `confidence_threshold`
of 0.7.

Everything else -- the MASK_DEV_MODE bootstrap, and the offset recovery for
tier-2 NLP hits that come back without start/end -- matches the India
adapter.
"""

from __future__ import annotations

import os
from typing import Any

from bench.indiapii.harness.offsets import locate_span

os.environ.setdefault("MASK_DEV_MODE", "true")


def _noop_encode(value: str, **_kwargs: Any) -> str:
    return "\x00"


class MaskPrivacyIntlAdapter:
    name = "mask_privacy"

    def __init__(self) -> None:
        self._scanner: Any = None
        self._unavailable_reason: str | None = None

    def available(self) -> tuple[bool, str]:
        if self._unavailable_reason is not None:
            return False, self._unavailable_reason
        if self._scanner is not None:
            return True, ""
        try:
            from mask_privacy import get_scanner

            scanner = get_scanner()
            scanner.scan_and_return_entities("smoke test, no PII here.", encode_fn=_noop_encode)
        except Exception as exc:  # noqa: BLE001
            self._unavailable_reason = f"mask-privacy init failed: {exc}"
            return False, self._unavailable_reason
        self._scanner = scanner
        return True, ""

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        entities = self._scanner.scan_and_return_entities(
            text, encode_fn=_noop_encode, confidence_threshold=0.7
        )
        used_starts: set[int] = set()
        found: list[tuple[int, int, str]] = []
        for e in entities:
            if e.get("start") is not None and e.get("end") is not None:
                used_starts.add(e["start"])
                found.append((e["start"], e["end"], e["type"]))
        for e in entities:
            if e.get("start") is not None and e.get("end") is not None:
                continue
            located = locate_span(text, e.get("value", ""), used_starts)
            if located is not None:
                found.append((located[0], located[1], e["type"]))
        return found
