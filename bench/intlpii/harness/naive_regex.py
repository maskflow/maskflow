"""The intl naive-regex baseline -- no checksum validation, no context, no
NER. Every pattern is a fixed, bounded shape (no nested quantifiers, no
catastrophic-backtracking risk): what a developer with no PII-detection
experience would write in an afternoon, not a strawman built to lose.

Mirrors bench.indiapii.harness.adapters.naive_regex_adapter for the intl
corpus's types.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL_SHAPED", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    (
        "PHONE_SHAPED",
        re.compile(r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
    ),
    ("SSN_SHAPED", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("CARD_SHAPED", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?<=\d)")),
    ("IPV4_SHAPED", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("AWS_KEY_SHAPED", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("JWT_SHAPED", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
)


class NaiveRegexIntlAdapter:
    name = "naive_regex"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        found: list[tuple[int, int, str]] = []
        for label, pattern in _PATTERNS:
            for m in pattern.finditer(text):
                found.append((m.start(), m.end(), label))
        return found
