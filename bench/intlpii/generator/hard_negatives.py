"""Confusable-but-not-PII value generators, one per spec'd hard-negative
category. Each returns a string; templates.py records it under a
shape-descriptive label (never a real registered PIIType), so a detector
that fires a real label on one of these spans is scored as a false
positive (see generate.py / maskflow_bench.matching).

Every generator here is engineered to fail the corresponding real
validator in maskflow_pack_intl.patterns -- see each function's comment
for which check it breaks, and identifiers.py for the "make it pass"
counterpart.
"""

from __future__ import annotations

import random
import string

CC_LUHN_INVALID = "CC_LUHN_INVALID"
SSN_INVALID_AREA = "SSN_INVALID_AREA"
IBAN_BAD_CHECKSUM = "IBAN_BAD_CHECKSUM"
ORDER_ID_SHAPED = "ORDER_ID_SHAPED"
TRACKING_NUMBER_SHAPED = "TRACKING_NUMBER_SHAPED"

ALL_LABELS = (
    CC_LUHN_INVALID,
    SSN_INVALID_AREA,
    IBAN_BAD_CHECKSUM,
    ORDER_ID_SHAPED,
    TRACKING_NUMBER_SHAPED,
)


def generate_cc_luhn_invalid(rng: random.Random) -> str:
    """16 digits in CREDIT_CARD_RE's shape, but the trailing digit is
    deliberately not the Luhn check digit -- validate_credit_card() returns
    None (patterns.py: `0.97 if luhn_is_valid(digits) else None`)."""
    from .identifiers import _luhn_check_digit  # noqa: PLC0415

    body = rng.choice(("4", "51", "37")) + "".join(rng.choice(string.digits) for _ in range(13))
    good = _luhn_check_digit(body[:15])
    bad = str((int(good) + rng.randint(1, 9)) % 10)
    return (body[:15] + bad)[:16]


def generate_ssn_invalid_area(rng: random.Random) -> str:
    """Dashed SSN shape with an area number the SSA never issues (000, 666,
    or 900-999) -- validate_ssn_dashed()/validate_ssn_plain() reject it."""
    area = rng.choice(("000", "666", f"9{rng.randint(0, 99):02d}"))
    return f"{area}-{rng.randint(1, 99):02d}-{rng.randint(1, 9999):04d}"


def generate_iban_bad_checksum(rng: random.Random) -> str:
    """IBAN shape and length, but random check digits -- iban_is_valid()
    (mod-97) fails, so validate_iban() returns None."""
    from .identifiers import _IBAN_SPECS, _iban_check_digits  # noqa: PLC0415

    country, total_len = rng.choice(list(_IBAN_SPECS.items()))
    bban = "".join(rng.choice(string.digits) for _ in range(total_len - 4))
    good = _iban_check_digits(country, bban)
    bad = f"{(int(good) + rng.randint(1, 20)) % 100:02d}"
    return f"{country}{bad}{bban}"


def generate_order_id_shaped(rng: random.Random) -> str:
    """Prefix + date + sequence order/ticket ID -- alphanumeric texture near
    API_KEY / AWS_KEY, but no pattern in the pack matches structurally. The
    sequence carries a letter on purpose: a bare 13-19 digit run would land
    in CREDIT_CARD_RE's window and pass Luhn ~1 time in 10, which is a decoy
    behaving like a different decoy, not the confusion this category tests."""
    prefix = rng.choice(("ORD", "TCK", "REF", "INV", "PO"))
    year = rng.randint(2023, 2026)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    seq = rng.choice(string.ascii_uppercase) + "".join(
        rng.choice(string.digits) for _ in range(rng.choice((4, 5)))
    )
    return f"{prefix}-{year}-{month:02d}{day:02d}-{seq}"


def generate_tracking_number_shaped(rng: random.Random) -> str:
    """A 12-22 digit courier tracking run -- long enough to sit in
    CREDIT_CARD_RE's 13-19 digit window sometimes, but Luhn-invalid by
    construction (retried until it fails) and never card-length-locked."""
    from maskflow_pack_intl.patterns import luhn_is_valid  # noqa: PLC0415

    while True:
        n = "".join(rng.choice(string.digits) for _ in range(rng.choice((12, 18, 20, 22))))
        if not (13 <= len(n) <= 19 and luhn_is_valid(n)):
            return n


GENERATORS = {
    CC_LUHN_INVALID: generate_cc_luhn_invalid,
    SSN_INVALID_AREA: generate_ssn_invalid_area,
    IBAN_BAD_CHECKSUM: generate_iban_bad_checksum,
    ORDER_ID_SHAPED: generate_order_id_shaped,
    TRACKING_NUMBER_SHAPED: generate_tracking_number_shaped,
}
