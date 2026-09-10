"""The naive log-regex baseline: fixed, bounded shapes, no validation, no
context, no NER -- what a developer greps their logs for in an afternoon.
Mirrors bench.indiapii.harness.adapters.naive_regex_adapter.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL_SHAPED", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("IPV4_SHAPED", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("CARD_SHAPED", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?<=\d)")),
    ("PHONE_SHAPED", re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}\b")),
    ("AADHAAR_SHAPED", re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}\b")),
    ("PAN_SHAPED", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("AWS_KEY_SHAPED", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("JWT_SHAPED", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
)


class NaiveLogRegexAdapter:
    name = "naive_regex"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        found: list[tuple[int, int, str]] = []
        for label, pattern in _PATTERNS:
            for m in pattern.finditer(text):
                found.append((m.start(), m.end(), label))
        return found
