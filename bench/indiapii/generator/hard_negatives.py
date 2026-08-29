"""Confusable-but-not-PII value generators, one per spec'd hard-negative
category. Each returns (text, label) where `label` is a shape-descriptive
tag, never a real registered PIIType -- a detector that fires any real
label on one of these spans is a false positive when the corpus is scored
(see generate.py / metrics.py).

Every generator here is deliberately built to fail the corresponding real
recognizer's validator (patterns.py) -- see each function's comment for
which check it's engineered to fail, and identifiers.py for the "make it
pass" counterpart.
"""

from __future__ import annotations

import random
import string

from maskflow_pack_india.checksums import verhoeff_is_valid
from maskflow_pack_india.patterns import _PAN_FOURTH_CHAR_CATEGORIES

NON_VERHOEFF_AADHAAR_SHAPED = "NON_VERHOEFF_AADHAAR_SHAPED"
PAN_SHAPED_INVOICE_NO = "PAN_SHAPED_INVOICE_NO"
VPA_SHAPED_EMAIL = "VPA_SHAPED_EMAIL"
ORDER_ID_SHAPED = "ORDER_ID_SHAPED"
TIMESTAMP_SHAPED = "TIMESTAMP_SHAPED"

ALL_LABELS = (
    NON_VERHOEFF_AADHAAR_SHAPED,
    PAN_SHAPED_INVOICE_NO,
    VPA_SHAPED_EMAIL,
    ORDER_ID_SHAPED,
    TIMESTAMP_SHAPED,
)

_COMPANY_WORDS = (
    "acmecorp",
    "bluepeak",
    "vertexsys",
    "nimbuscloud",
    "starlinelogistics",
    "orbitretail",
    "swiftfin",
    "clearpathhq",
)


def generate_non_verhoeff_aadhaar(rng: random.Random) -> str:
    """12 digits, first digit 2-9 (AADHAAR's own shape), but with the
    trailing check digit deliberately wrong -- fails verhoeff_is_valid, so
    validate_aadhaar() rejects it (patterns.py: `0.9 if verhoeff_is_valid
    (digits) else None`)."""
    while True:
        digits = rng.choice("23456789") + "".join(rng.choice(string.digits) for _ in range(11))
        if not verhoeff_is_valid(digits):
            return digits


def generate_pan_shaped_invoice_no(rng: random.Random) -> str:
    """5 letters + 4 digits + 1 letter (PAN's exact shape), but the 4th
    letter is deliberately chosen OUTSIDE PAN's holder-category set, so
    validate_pan() rejects it (patterns.py: `if value[3] not in
    _PAN_FOURTH_CHAR_CATEGORIES: return None`)."""
    invalid_fourth = [c for c in string.ascii_uppercase if c not in _PAN_FOURTH_CHAR_CATEGORIES]
    letters = [rng.choice(string.ascii_uppercase) for _ in range(5)]
    letters[3] = rng.choice(invalid_fourth)
    digits = "".join(rng.choice(string.digits) for _ in range(4))
    checksum_letter = rng.choice(string.ascii_uppercase)
    return "".join(letters) + digits + checksum_letter


def generate_vpa_shaped_email(rng: random.Random) -> str:
    """handle@singleword -- matches UPI_VPA_RE's shape (no dot in the
    domain part) but the domain is a made-up company word, never a real
    NPCI-issued PSP handle, so validate_upi_vpa() rejects it (handle not in
    UPI_PSP_HANDLES)."""
    handle_len = rng.randint(4, 12)
    handle = "".join(rng.choice(string.ascii_lowercase + ".") for _ in range(handle_len)).strip(".")
    domain = rng.choice(_COMPANY_WORDS)
    return f"{handle}@{domain}"


def generate_order_id_shaped(rng: random.Random) -> str:
    """Alphanumeric order/ticket ID -- shares PAN/GSTIN's mixed
    letter-digit texture but in a different arrangement (prefix + date +
    sequence) no India-PII pattern in this pack matches structurally."""
    prefix = rng.choice(("ORD", "TCK", "REF", "INV"))
    date_part = f"{rng.randint(2023, 2026)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    seq = "".join(rng.choice(string.digits) for _ in range(4))
    return f"{prefix}-{date_part}-{seq}"


def generate_timestamp_shaped(rng: random.Random) -> str:
    """Either an ISO-ish datetime or a bare 13-digit epoch-millis run --
    the latter is close enough in raw digit-count to AADHAAR/BANK_ACCOUNT_IN
    to be a genuinely confusable bare digit run, but has no separators, no
    Verhoeff structure, and no account/aadhaar context keyword nearby."""
    if rng.random() < 0.5:
        year = rng.randint(2023, 2026)
        month, day = rng.randint(1, 12), rng.randint(1, 28)
        hour, minute, second = rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
        return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"
    return str(rng.randint(1_700_000_000_000, 1_900_000_000_000))


GENERATORS = {
    NON_VERHOEFF_AADHAAR_SHAPED: generate_non_verhoeff_aadhaar,
    PAN_SHAPED_INVOICE_NO: generate_pan_shaped_invoice_no,
    VPA_SHAPED_EMAIL: generate_vpa_shaped_email,
    ORDER_ID_SHAPED: generate_order_id_shaped,
    TIMESTAMP_SHAPED: generate_timestamp_shaped,
}
