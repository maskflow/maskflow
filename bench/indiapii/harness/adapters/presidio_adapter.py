"""Adapter 2: Presidio, entirely out of the box -- no custom recognizers.

Explicitly pins the spaCy model to en_core_web_sm (the same model
.github/workflows/ci.yml already downloads for pack-intl/pack-india) rather
than Presidio's own default of en_core_web_lg, which this environment
doesn't have installed. No India-specific recognizer exists in stock
Presidio, so AADHAAR/PAN/GSTIN/IFSC/UPI_VPA/etc. are expected to score
zero recall here -- that gap is the entire point of the comparison, not a
harness bug.
"""

from __future__ import annotations

from typing import Any


class PresidioAdapter:
    name = "presidio_oob"

    def __init__(self) -> None:
        self._engine: Any = None
        self._unavailable_reason: str | None = None

    def _build_engine(self) -> Any:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        conf = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=conf).create_engine()
        return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

    def available(self) -> tuple[bool, str]:
        if self._unavailable_reason is not None:
            return False, self._unavailable_reason
        if self._engine is not None:
            return True, ""
        try:
            self._engine = self._build_engine()
        except Exception as exc:  # noqa: BLE001 -- any init failure just skips this adapter
            self._unavailable_reason = f"presidio init failed: {exc}"
            return False, self._unavailable_reason
        return True, ""

    @property
    def engine(self) -> Any:
        """The built AnalyzerEngine, for presidio_custom_adapter.py to add
        its own recognizers to. Only meaningful after available() is True."""
        return self._engine

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        results = self._engine.analyze(text=text, language="en")
        return [(r.start, r.end, r.entity_type) for r in results]
