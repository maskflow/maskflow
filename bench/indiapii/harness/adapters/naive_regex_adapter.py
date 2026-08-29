"""Adapter 5: the naive-regex baseline -- deliberately no checksum
validation, no context awareness, no NER. Every pattern below is a fixed,
bounded shape (no nested quantifiers, no catastrophic-backtracking risk)
-- this is meant to be what a developer with zero PII-detection experience
would write in an afternoon, not a strawman built to lose.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PHONE_SHAPED", re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}\b")),
    ("AADHAAR_SHAPED", re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}\b")),
    ("PAN_SHAPED", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("PINCODE_SHAPED", re.compile(r"\b\d{6}\b")),
)


class NaiveRegexAdapter:
    name = "naive_regex"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        found: list[tuple[int, int, str]] = []
        for label, pattern in _PATTERNS:
            for m in pattern.finditer(text):
                found.append((m.start(), m.end(), label))
        return found
