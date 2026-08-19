"""Regex patterns and structural validators for each PII type.

Each entry in PATTERNS maps a PIIType to (compiled_regex, base_confidence, validator).
`validator(value) -> float | None` returns an adjusted confidence, or None to reject
the match entirely (e.g. a 16-digit number that fails the Luhn check).
"""
import re

from .entities import PIIType

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
)

SSN_DASHED_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
SSN_PLAIN_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")

CREDIT_CARD_RE = re.compile(
    r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)"
)

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

JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
)

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


def _validate_credit_card(value: str) -> float | None:
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


def _validate_iban(value: str) -> float | None:
    return 0.9 if iban_is_valid(value) else None


def _validate_ssn_dashed(value: str) -> float | None:
    area = value[:3]
    if area in ("000", "666") or area.startswith("9"):
        return None
    return 0.95


def _validate_ssn_plain(value: str) -> float | None:
    # Bare 9-digit numbers are ambiguous (order IDs, phone numbers without
    # formatting, etc.) -- start low, let context.py decide if it's really an SSN.
    return 0.35


# type -> (regex, base_confidence, validator)
PATTERNS: dict[PIIType, list[tuple[re.Pattern, float, "callable | None"]]] = {
    PIIType.EMAIL: [(EMAIL_RE, 0.95, None)],
    PIIType.PHONE: [(PHONE_RE, 0.85, None)],
    PIIType.SSN: [
        (SSN_DASHED_RE, 0.95, _validate_ssn_dashed),
        (SSN_PLAIN_RE, 0.35, _validate_ssn_plain),
    ],
    PIIType.CREDIT_CARD: [(CREDIT_CARD_RE, 0.9, _validate_credit_card)],
    PIIType.IP_ADDRESS: [(IPV4_RE, 0.75, None), (IPV6_RE, 0.85, None)],
    PIIType.AWS_KEY: [(AWS_KEY_RE, 0.97, None)],
    PIIType.API_KEY: [
        (API_KEY_RE, 0.95, None),
        (GENERIC_SECRET_ASSIGNMENT_RE, 0.6, None),
    ],
    PIIType.JWT: [(JWT_RE, 0.9, None)],
    PIIType.IBAN: [(IBAN_RE, 0.6, _validate_iban)],
    PIIType.ADDRESS: [(ADDRESS_RE, 0.7, None)],
}
