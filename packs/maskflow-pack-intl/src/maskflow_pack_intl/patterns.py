"""Regex patterns and structural validators for each intl PII type.

Each validator(value) -> float | None returns an adjusted confidence, or None
to reject the match entirely (e.g. a 16-digit number that fails the Luhn
check). __init__.py registers these against maskflow-core via register_pattern().
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")

SSN_DASHED_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
SSN_PLAIN_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")

CREDIT_CARD_RE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")

IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
IPV6_RE = re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}\b")

AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")

API_KEY_RE = re.compile(
    r"\b(?:sk-ant-[A-Za-z0-9_-]{20,}"
    r"|sk-[A-Za-z0-9_-]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[A-Za-z0-9_-]{35})\b"
)

GENERIC_SECRET_ASSIGNMENT_RE = re.compile(
    # \w* bounded to \w{0,40} -- unbounded quantifiers flanking an alternation,
    # scanned via finditer from every offset, are O(n^2) on a long word-run
    # with no ":"/"=" (e.g. a big pasted alnum/base64 blob). See test_regex_safety.py.
    r"(?i)\b\w{0,40}(?:key|secret|token|password|credential)\w{0,40}"
    r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-/+]{16,})['\"]?"
)

JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")

IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")

ADDRESS_RE = re.compile(
    # The outer {1,4} must stay bounded -- it caps backtracking on the nested
    # unbounded [a-zA-Z]* inside it. Widening to {1,} would make this pattern
    # vulnerable to catastrophic backtracking.
    r"\b\d{1,6}\s+(?:[A-Z][a-zA-Z]*\s){1,4}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|"
    r"Drive|Dr|Court|Ct|Way|Place|Pl|Terrace|Ter)\.?\b"
    r"(?:,?\s+(?:Apt|Suite|Ste|Unit)\.?\s*#?\w+)?"
)


def luhn_is_valid(digits: str) -> bool:
    digits = [int(d) for d in digits]
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def validate_credit_card(value: str) -> float | None:
    digits = re.sub(r"[ -]", "", value)
    if not (13 <= len(digits) <= 19) or not digits.isdigit():
        return None
    return 0.97 if luhn_is_valid(digits) else None


def iban_is_valid(value: str) -> bool:
    value = value.upper()
    rearranged = value[4:] + value[:4]
    converted = "".join(str(int(c, 36)) for c in rearranged)
    try:
        return int(converted) % 97 == 1
    except ValueError:
        return False


def validate_iban(value: str) -> float | None:
    return 0.9 if iban_is_valid(value) else None


def validate_ssn_dashed(value: str) -> float | None:
    area = value[:3]
    if area in ("000", "666") or area.startswith("9"):
        return None
    return 0.95


def validate_ssn_plain(value: str) -> float | None:
    # Bare 9-digit numbers are ambiguous (order IDs, phone numbers without
    # formatting, etc.) -- start low, let context.py decide if it's really an SSN.
    # Still apply the same area-code structural check as the dashed form, so
    # this validator can actually reject something (a no-op validator that
    # never returns None isn't a real structural check, and shouldn't be able
    # to claim `validated=True` priority during overlap resolution).
    area = value[:3]
    if area in ("000", "666") or area.startswith("9"):
        return None
    return 0.35
