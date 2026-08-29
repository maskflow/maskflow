"""Strategy.SURROGATE fake-value generators for this pack's own entity
types. Each is a `(original: str, rng: random.Random) -> str` callable
registered via `registry.register_surrogate_generator()` in __init__.py --
`masking.py`'s `surrogate_substitute()` calls it with the real matched
span text (so shape/format cues like separators or a "+91" prefix can be
preserved) and a fresh `secrets.SystemRandom()` instance per call.

Every value is checksum-VALID (where the type has a published checksum --
AADHAAR via Verhoeff, GSTIN via its mod-36 scheme) or structurally valid to
its documented format (where it doesn't), built the same way
bench/indiapii/generator/identifiers.py builds this pack's own synthetic
benchmark corpus -- uniformly random subject only to the format/checksum
constraint, never drawn from or checked against a real-world registry.
There is no publicly reserved "test" range for Indian identifiers (unlike,
say, Stripe's published test card numbers), so "never a real assignee" here
means exactly what it means for the benchmark corpus: random within the
valid shape, nothing more.
"""

from __future__ import annotations

import random
import re
import string

from .checksums import gstin_checksum_char, verhoeff_generate
from .data.ifsc_bank_codes import IFSC_BANK_CODES
from .data.indian_names import load_indian_names
from .data.indian_places import INDIAN_CITIES, INDIAN_STATE_UT_NAMES
from .data.indian_state_rto_codes import INDIAN_STATE_RTO_CODES
from .data.upi_handles import UPI_PSP_HANDLES
from .patterns import _PAN_FOURTH_CHAR_CATEGORIES

_IFSC_CODES = sorted(IFSC_BANK_CODES)
_RTO_CODES = sorted(INDIAN_STATE_RTO_CODES)
_UPI_HANDLES = sorted(UPI_PSP_HANDLES)
_STATES_TITLE = tuple(s.title() for s in INDIAN_STATE_UT_NAMES)

_ALNUM_UPPER = string.ascii_uppercase + string.digits
_UNIT_MARKERS = ("H.No.", "Flat", "Plot", "Sector", "Block", "Phase", "Door No.")
_LOCALITY_SUFFIXES = ("Nagar", "Colony", "Vihar", "Puram", "Layout", "Extension", "Marg")

_SEP_RE = re.compile(r"[ -]")
_DIGITS_RE = re.compile(r"\d")


def _digits(rng: random.Random, n: int, first: str = "0123456789") -> str:
    return rng.choice(first) + "".join(rng.choice(string.digits) for _ in range(n - 1))


def _match_separator(original: str, rng: random.Random) -> str:
    """Reuse whatever spacing/hyphenation `original` used, so a surrogate
    dropped into the same sentence doesn't visibly change punctuation
    style -- falls back to a random choice when `original` has none (a
    fully unspaced value)."""
    m = _SEP_RE.search(original)
    return m.group(0) if m else rng.choice(("", " ", "-"))


def surrogate_person_name(original: str, rng: random.Random) -> str:
    names = list(load_indian_names().keys())
    k = min(len(original.split()), 2) or 1
    parts = rng.sample(names, k=k)
    return " ".join(p.title() for p in parts)


def surrogate_aadhaar(original: str, rng: random.Random) -> str:
    # Preserve UID (12-digit) vs VID (16-digit) shape based on how many
    # digits the matched span actually had.
    n_digits = len(_DIGITS_RE.findall(original))
    length = 16 if n_digits > 12 else 12
    base = _digits(rng, length - 1, first="23456789")
    full = base + verhoeff_generate(base)
    sep = _match_separator(original, rng)
    groups = [full[i : i + 4] for i in range(0, length, 4)]
    return sep.join(groups)


def surrogate_aadhaar_masked(original: str, rng: random.Random) -> str:
    last4 = _digits(rng, 4)
    mask_char = next((c for c in original if c in "Xx*"), rng.choice(("X", "x", "*")))
    sep = _match_separator(original, rng)
    return f"{mask_char * 4}{sep}{mask_char * 4}{sep}{last4}"


def surrogate_pan(original: str, rng: random.Random) -> str:
    letters = [rng.choice(string.ascii_uppercase) for _ in range(5)]
    letters[3] = rng.choice(_PAN_FOURTH_CHAR_CATEGORIES)
    digits = "".join(rng.choice(string.digits) for _ in range(4))
    checksum_letter = rng.choice(string.ascii_uppercase)
    return "".join(letters) + digits + checksum_letter


def surrogate_gstin(original: str, rng: random.Random) -> str:
    state_code = f"{rng.randint(1, 38):02d}"
    pan = surrogate_pan(original, rng)
    entity_number = rng.choice(string.digits[1:])
    first_14 = state_code + pan + entity_number + "Z"
    return first_14 + gstin_checksum_char(first_14)


def surrogate_ifsc(original: str, rng: random.Random) -> str:
    bank_code = rng.choice(_IFSC_CODES)
    branch = "".join(rng.choice(_ALNUM_UPPER) for _ in range(6))
    return f"{bank_code}0{branch}"


def surrogate_upi_vpa(original: str, rng: random.Random) -> str:
    handle_len = rng.randint(4, 14)
    handle = "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(handle_len))
    psp = rng.choice(_UPI_HANDLES)
    return f"{handle}@{psp}"


def surrogate_indian_mobile(original: str, rng: random.Random) -> str:
    number = rng.choice("6789") + "".join(rng.choice(string.digits) for _ in range(9))
    if original.startswith("+91"):
        sep = original[3] if len(original) > 3 and original[3] in " -" else ""
        return f"+91{sep}{number}"
    if original.startswith("0"):
        return f"0{number}"
    return number


def surrogate_pin_code(original: str, rng: random.Random) -> str:
    return rng.choice("12345678") + "".join(rng.choice(string.digits) for _ in range(5))


def surrogate_voter_id(original: str, rng: random.Random) -> str:
    letters = "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    digits = "".join(rng.choice(string.digits) for _ in range(7))
    return letters + digits


def surrogate_indian_passport(original: str, rng: random.Random) -> str:
    if "\n" in original:
        # MRZ block: keep it simple and format-valid rather than trying to
        # preserve the original name field -- the surrogate condition only
        # needs "a different, still-valid-shaped identifier", not a
        # semantically matched replacement.
        from .checksums import mrz_line1_generate, mrz_line2_generate

        names = list(load_indian_names().keys())
        surname, given = rng.sample(names, k=2)
        line1 = mrz_line1_generate(surname, given)
        passport_no = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(9))
        dob = f"{rng.randint(60, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
        expiry = f"{rng.randint(24, 35):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
        line2 = mrz_line2_generate(passport_no, dob, expiry)
        return f"{line1}\n{line2}"
    valid_letters = [c for c in string.ascii_uppercase if c not in "QXZ"]
    letter = rng.choice(valid_letters)
    d1 = rng.choice(string.digits[1:])
    d2 = rng.choice(string.digits)
    mid4 = "".join(rng.choice(string.digits) for _ in range(4))
    dlast = rng.choice(string.digits[1:])
    space = " " if " " in original else ""
    return f"{letter}{d1}{d2}{space}{mid4}{dlast}"


def surrogate_driving_licence(original: str, rng: random.Random) -> str:
    state_code = rng.choice(_RTO_CODES)
    office = f"{rng.randint(1, 99):02d}"
    year = str(rng.randint(1980, 2024))
    serial = "".join(rng.choice(string.digits) for _ in range(7))
    sep = _match_separator(original, rng)
    return f"{state_code}{office}{sep}{year}{sep}{serial}"


def surrogate_vehicle_reg(original: str, rng: random.Random) -> str:
    state_code = rng.choice(_RTO_CODES)
    office = str(rng.randint(1, 99))
    series = "".join(rng.choice(string.ascii_uppercase) for _ in range(rng.choice((1, 2))))
    number = "".join(rng.choice(string.digits) for _ in range(4))
    sep = _match_separator(original, rng)
    return f"{state_code}{sep}{office}{sep}{series}{sep}{number}"


def surrogate_abha_number(original: str, rng: random.Random) -> str:
    digits = _digits(rng, 14, first="123456789")
    sep = _match_separator(original, rng) or "-"
    return f"{digits[0:2]}{sep}{digits[2:6]}{sep}{digits[6:10]}{sep}{digits[10:14]}"


def surrogate_abha_address(original: str, rng: random.Random) -> str:
    handle_len = rng.randint(4, 14)
    handle = "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(handle_len))
    domain = rng.choice(("abdm", "sbx"))
    return f"{handle}@{domain}"


def surrogate_bank_account(original: str, rng: random.Random) -> str:
    length = len(original) if original.isdigit() else rng.randint(9, 18)
    return _digits(rng, length, first="123456789")


def surrogate_indian_address(original: str, rng: random.Random) -> str:
    unit = rng.choice(_UNIT_MARKERS)
    unit_no = f"{rng.randint(1, 999)}{rng.choice(('', 'A', 'B'))}"
    locality = f"{surrogate_person_name(original, rng).split()[0]} {rng.choice(_LOCALITY_SUFFIXES)}"
    city = rng.choice(INDIAN_CITIES)
    state = rng.choice(_STATES_TITLE)
    return f"{unit} {unit_no}, {locality}, {city}, {state}"
