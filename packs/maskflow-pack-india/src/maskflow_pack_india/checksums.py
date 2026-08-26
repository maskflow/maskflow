"""Verhoeff (AADHAAR) and GSTIN check-digit algorithms, isolated from regex/
registration concerns so they can be unit-tested against published test
vectors on their own (see tests/test_checksums.py).

Neither algorithm is invented here -- both are the standard published
constants/procedures (Verhoeff: Wikipedia "Verhoeff algorithm" / ISO
reference tables; GSTIN: GSTN's published Luhn-mod-36 check-digit scheme,
reimplemented independently by several open gstin-validator packages).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Verhoeff checksum -- dihedral group D5 multiplication/permutation tables.
# ---------------------------------------------------------------------------

_D5_MULT: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

_D5_PERM: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

_D5_INV: tuple[int, ...] = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_is_valid(digits: str) -> bool:
    """`digits` is the FULL number (AADHAAR UID or VID) including its
    trailing Verhoeff check digit. Processed right-to-left; valid iff the
    accumulator lands on 0. Caller is responsible for length/digit-only
    checks -- this raises ValueError on a non-digit character rather than
    silently misjudging it, since `int(ch)` would otherwise be the only
    signal something was wrong."""
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D5_MULT[c][_D5_PERM[i % 8][int(ch)]]
    return c == 0


def verhoeff_generate(digits: str) -> str:
    """Given digits WITHOUT a check digit, return the check digit that makes
    `verhoeff_is_valid(digits + check_digit)` True. Not used by the
    recognizer itself (nothing needs to *produce* a checksum at detection
    time) -- exists so tests/fixtures can build synthetic, checksum-valid
    AADHAAR-shaped values without hand-computing them."""
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D5_MULT[c][_D5_PERM[(i + 1) % 8][int(ch)]]
    return str(_D5_INV[c])


# ---------------------------------------------------------------------------
# GSTIN checksum -- Luhn-mod-36 variant: alternating weights (2, 1, 2, 1, ...)
# right-to-left over the 36-char alphanumeric alphabet, with base-36
# digit-sum folding (the base-36 analogue of Luhn's "subtract 9 if > 9").
# ---------------------------------------------------------------------------

_GST_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GST_MOD = 36


def gstin_checksum_char(first_14: str) -> str:
    """Compute the 15th (check) character for the first 14 GSTIN characters."""
    total = 0
    factor = 2
    for ch in reversed(first_14):
        value = _GST_ALPHABET.index(ch)
        product = factor * value
        total += (product // _GST_MOD) + (product % _GST_MOD)
        factor = 1 if factor == 2 else 2
    check_value = (_GST_MOD - (total % _GST_MOD)) % _GST_MOD
    return _GST_ALPHABET[check_value]


def gstin_is_valid(gstin: str) -> bool:
    """`gstin` is the full 15-character value. Caller is responsible for the
    other structural checks (state code range, embedded-PAN shape, the
    literal 'Z') -- this only verifies the 15th-character checksum."""
    if len(gstin) != 15:
        return False
    try:
        return gstin[14] == gstin_checksum_char(gstin[:14])
    except ValueError:
        # gstin[:14] contains a character outside _GST_ALPHABET (e.g.
        # lowercase, punctuation) -- not a valid GSTIN shape, not a bug.
        return False
