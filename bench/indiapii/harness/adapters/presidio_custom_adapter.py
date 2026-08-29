"""Adapter 3: Presidio + two hand-added Aadhaar/PAN PatternRecognizers.

"Scrupulously fair" per the work order: the checksum/structural validation
these recognizers apply is the pack's own real validator
(maskflow_pack_india.patterns.validate_aadhaar / validate_pan), not a
deliberately weak stand-in -- same correctness bar as MaskFlow's own
Aadhaar/PAN recognizers, genuinely different architecture (Presidio's
context-window scoring engine, not MaskFlow's confidence/resolution
pipeline). The regex shapes themselves are the same well-known Aadhaar/PAN
patterns maskflow_pack_india.patterns uses, written independently here as
plain strings for Presidio's Pattern API (no shared code with core).
"""

from __future__ import annotations

from typing import Any

from .presidio_adapter import PresidioAdapter

_AADHAAR_REGEX = r"(?<!\d)[2-9]\d{3}([ -]?)\d{4}\1\d{4}(?!\d)"
_PAN_REGEX = r"(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])"


def _build_aadhaar_recognizer() -> Any:
    from maskflow_pack_india.patterns import validate_aadhaar
    from presidio_analyzer import Pattern, PatternRecognizer

    class AadhaarRecognizer(PatternRecognizer):
        def validate_result(self, pattern_text: str) -> bool | None:
            digits = pattern_text.replace(" ", "").replace("-", "")
            return validate_aadhaar(digits) is not None

    return AadhaarRecognizer(
        supported_entity="IN_AADHAAR",
        patterns=[Pattern("Aadhaar (Verhoeff-validated)", _AADHAAR_REGEX, 0.5)],
        context=["aadhaar", "aadhar", "uidai"],
    )


def _build_pan_recognizer() -> Any:
    from maskflow_pack_india.patterns import validate_pan
    from presidio_analyzer import Pattern, PatternRecognizer

    class PanRecognizer(PatternRecognizer):
        def validate_result(self, pattern_text: str) -> bool | None:
            return validate_pan(pattern_text) is not None

    return PanRecognizer(
        supported_entity="IN_PAN",
        patterns=[Pattern("PAN (holder-category validated)", _PAN_REGEX, 0.6)],
        context=["pan", "permanent account number"],
    )


class PresidioCustomAdapter:
    name = "presidio_custom"

    def __init__(self) -> None:
        self._base = PresidioAdapter()
        self._registered = False
        self._unavailable_reason: str | None = None

    def available(self) -> tuple[bool, str]:
        if self._unavailable_reason is not None:
            return False, self._unavailable_reason
        ok, reason = self._base.available()
        if not ok:
            self._unavailable_reason = reason
            return False, reason
        if not self._registered:
            try:
                registry = self._base.engine.registry
                registry.add_recognizer(_build_aadhaar_recognizer())
                registry.add_recognizer(_build_pan_recognizer())
                self._registered = True
            except Exception as exc:  # noqa: BLE001
                self._unavailable_reason = f"custom recognizer registration failed: {exc}"
                return False, self._unavailable_reason
        return True, ""

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        results = self._base.engine.analyze(text=text, language="en")
        return [(r.start, r.end, r.entity_type) for r in results]
