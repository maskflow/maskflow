"""Verhoeff (AADHAAR), GSTIN, and MRZ (passport) check-digit algorithms,
isolated from regex/registration concerns so they can be unit-tested against
published test vectors on their own (see tests/test_checksums.py).

None of these algorithms are invented here -- all are standard published
constants/procedures (Verhoeff: Wikipedia "Verhoeff algorithm" / ISO
reference tables; GSTIN: GSTN's published Luhn-mod-36 check-digit scheme,
reimplemented independently by several open gstin-validator packages; MRZ:
ICAO Doc 9303 Part 4's weighted 7-3-1 mod-10 check-digit algorithm, the same
scheme used on every ICAO-compliant machine-readable passport worldwide).
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


# ---------------------------------------------------------------------------
# MRZ (Machine Readable Zone) -- ICAO Doc 9303 Part 4's check-digit scheme:
# weights 7, 3, 1 cycling left-to-right, digit chars valued 0-9, 'A'-'Z'
# valued 10-35, '<' (filler) valued 0, summed and reduced mod 10. Applied
# independently to a TD3 passport MRZ's document-number, DOB, and
# expiry-date fields, plus once more to a composite field built from all
# three (see indian_passport_mrz_line2_is_valid below).
# ---------------------------------------------------------------------------

_MRZ_WEIGHTS: tuple[int, int, int] = (7, 3, 1)


def _mrz_char_value(ch: str) -> int:
    if ch.isdigit():
        return int(ch)
    if ch == "<":
        return 0
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    raise ValueError(f"character outside the MRZ alphabet: {ch!r}")


def mrz_check_digit(field: str) -> str:
    """Compute the ICAO 9303 check digit for `field` (a name-plus-filler,
    date, or composite MRZ field). Raises ValueError if `field` contains a
    character outside [A-Z0-9<] -- callers here always run this after a
    regex has already constrained the alphabet, so that indicates a caller
    bug, not adversarial input."""
    total = 0
    for i, ch in enumerate(field):
        total += _mrz_char_value(ch) * _MRZ_WEIGHTS[i % 3]
    return str(total % 10)


def indian_passport_mrz_line2_is_valid(line2: str) -> bool:
    """`line2` is the full 44-character TD3 second line (document number,
    nationality, DOB, sex, expiry, optional personal number, and their check
    digits -- see patterns.py's INDIAN_PASSPORT_MRZ_RE for the field-offset
    reference). Verifies all four check digits: document number, DOB,
    expiry, and the composite over document-number+check, DOB+check,
    expiry+check, and personal-number+check. Caller is responsible for the
    regex-level shape/country-code check; this only verifies checksums."""
    if len(line2) != 44:
        return False
    passport_no, passport_check = line2[0:9], line2[9]
    # line2[10:13] is the nationality field ("IND"), already regex-pinned.
    dob, dob_check = line2[13:19], line2[19]
    # line2[20] is sex (M/F/<), not checksummed.
    expiry, expiry_check = line2[21:27], line2[27]
    personal_no, personal_check = line2[28:42], line2[42]
    composite_check = line2[43]
    composite_field = (
        passport_no
        + passport_check
        + dob
        + dob_check
        + expiry
        + expiry_check
        + personal_no
        + personal_check
    )
    try:
        if mrz_check_digit(passport_no) != passport_check:
            return False
        if mrz_check_digit(dob) != dob_check:
            return False
        if mrz_check_digit(expiry) != expiry_check:
            return False
        # ICAO 9303 Part 4 allows an issuer to write '<' rather than a
        # computed digit when the optional personal-number field is
        # entirely unused -- accept either form, but a *present* personal
        # number's own check digit is still verified.
        if personal_check != "<" and mrz_check_digit(personal_no) != personal_check:
            return False
        return mrz_check_digit(composite_field) == composite_check
    except ValueError:
        return False


def mrz_line1_generate(surname: str, given_names: str) -> str:
    """Build a synthetic, well-formed TD3 first line ("P<IND<name field>")
    for a given surname/given-names pair. Line 1 carries no check digit --
    exists purely so tests/fixtures can build a synthetic MRZ block without
    hand-counting filler characters."""
    name_field = (surname.upper() + "<<" + given_names.upper()).replace(" ", "<")
    name_field = name_field.ljust(39, "<")[:39]
    return "P<IND" + name_field


def mrz_line2_generate(
    passport_no: str, dob: str, expiry: str, personal_no: str = "", sex: str = "M"
) -> str:
    """Given the non-checksum fields of a TD3 second line (`passport_no`
    padded/truncated to 9 chars, `dob`/`expiry` as 6-digit YYMMDD strings,
    optional `personal_no` padded/truncated to 14 chars), return the full
    44-char line with all four ICAO check digits computed. Not used by the
    recognizer itself -- exists so tests/fixtures can build synthetic,
    checksum-valid MRZ blocks without hand-computing check digits."""
    passport_no = passport_no.ljust(9, "<")[:9]
    personal_no = personal_no.ljust(14, "<")[:14]
    passport_check = mrz_check_digit(passport_no)
    dob_check = mrz_check_digit(dob)
    expiry_check = mrz_check_digit(expiry)
    personal_check = mrz_check_digit(personal_no)
    composite_field = (
        passport_no
        + passport_check
        + dob
        + dob_check
        + expiry
        + expiry_check
        + personal_no
        + personal_check
    )
    composite_check = mrz_check_digit(composite_field)
    return (
        passport_no
        + passport_check
        + "IND"
        + dob
        + dob_check
        + sex
        + expiry
        + expiry_check
        + personal_no
        + personal_check
        + composite_check
    )
