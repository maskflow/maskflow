"""One generate_<TYPE>(rng) -> str per registered maskflow-pack-india label.

Every value returned here is checksum-VALID (where the label has a published
checksum) or structurally valid to its documented format (where it doesn't)
-- see this package's __init__.py docstring for the corpus-wide guarantee
and generate.py for the self-check that verifies it against the pack's own
validate_*() functions rather than trusting this module blindly.

No value is ever drawn from or checked against a real-world registry: state
codes, bank codes, RTO codes, and UPI PSP handles come from the bundled
reference data (real, published *format* information), but the identifier
itself (the 10 PAN characters, the 9 IFSC branch-code characters, ...) is
uniformly random subject only to the format/checksum constraint.
"""

from __future__ import annotations

import random
import string

from maskflow_pack_india.checksums import gstin_checksum_char, verhoeff_generate
from maskflow_pack_india.data.ifsc_bank_codes import IFSC_BANK_CODES
from maskflow_pack_india.data.indian_names import load_indian_names
from maskflow_pack_india.data.indian_places import INDIAN_CITIES, INDIAN_STATE_UT_NAMES
from maskflow_pack_india.data.indian_state_rto_codes import INDIAN_STATE_RTO_CODES
from maskflow_pack_india.data.upi_handles import UPI_PSP_HANDLES
from maskflow_pack_india.patterns import _PAN_FOURTH_CHAR_CATEGORIES

_IFSC_CODES = sorted(IFSC_BANK_CODES)
_RTO_CODES = sorted(INDIAN_STATE_RTO_CODES)
_UPI_HANDLES = sorted(UPI_PSP_HANDLES)
_CITIES = INDIAN_CITIES
_STATES_TITLE = tuple(s.title() for s in INDIAN_STATE_UT_NAMES)

_ALNUM_UPPER = string.ascii_uppercase + string.digits

_UNIT_MARKERS = ("H.No.", "Flat", "Plot", "Sector", "Block", "Phase", "Door No.")
_LOCALITY_SUFFIXES = ("Nagar", "Colony", "Vihar", "Puram", "Layout", "Extension", "Marg")


def _digits(rng: random.Random, n: int, *, first: str = "0123456789") -> str:
    return rng.choice(first) + "".join(rng.choice(string.digits) for _ in range(n - 1))


def _sep(rng: random.Random) -> str:
    return rng.choice(("", " ", "-"))


def generate_person_name(rng: random.Random) -> str:
    names = list(load_indian_names().keys())
    parts = rng.sample(names, k=rng.choice((1, 2)))
    return " ".join(p.title() for p in parts)


def generate_aadhaar(rng: random.Random) -> str:
    base = _digits(rng, 11, first="23456789")
    full = base + verhoeff_generate(base)
    sep = _sep(rng)
    return f"{full[0:4]}{sep}{full[4:8]}{sep}{full[8:12]}"


def generate_aadhaar_vid(rng: random.Random) -> str:
    base = _digits(rng, 15, first="23456789")
    full = base + verhoeff_generate(base)
    sep = _sep(rng)
    return f"{full[0:4]}{sep}{full[4:8]}{sep}{full[8:12]}{sep}{full[12:16]}"


def generate_aadhaar_masked(rng: random.Random) -> str:
    last4 = _digits(rng, 4, first="0123456789")
    mask_char = rng.choice(("X", "x", "*"))
    sep = _sep(rng)
    return f"{mask_char * 4}{sep}{mask_char * 4}{sep}{last4}"


def generate_pan(rng: random.Random) -> str:
    letters = [rng.choice(string.ascii_uppercase) for _ in range(5)]
    letters[3] = rng.choice(_PAN_FOURTH_CHAR_CATEGORIES)
    digits = "".join(rng.choice(string.digits) for _ in range(4))
    checksum_letter = rng.choice(string.ascii_uppercase)
    return "".join(letters) + digits + checksum_letter


def generate_gstin(rng: random.Random) -> str:
    state_code = f"{rng.randint(1, 38):02d}"
    pan = generate_pan(rng)
    entity_number = rng.choice(string.digits[1:])
    first_14 = state_code + pan + entity_number + "Z"
    return first_14 + gstin_checksum_char(first_14)


def generate_ifsc(rng: random.Random) -> str:
    bank_code = rng.choice(_IFSC_CODES)
    branch = "".join(rng.choice(_ALNUM_UPPER) for _ in range(6))
    return f"{bank_code}0{branch}"


def generate_upi_vpa(rng: random.Random) -> str:
    handle_len = rng.randint(4, 14)
    handle = "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(handle_len))
    psp = rng.choice(_UPI_HANDLES)
    return f"{handle}@{psp}"


def generate_indian_mobile(rng: random.Random, *, with_prefix: bool = True) -> str:
    number = rng.choice("6789") + "".join(rng.choice(string.digits) for _ in range(9))
    if not with_prefix:
        return number
    prefix = rng.choice(("+91", "+91-", "+91 ", "0"))
    return prefix + number


def generate_pin_code(rng: random.Random) -> str:
    return rng.choice("12345678") + "".join(rng.choice(string.digits) for _ in range(5))


def generate_voter_id(rng: random.Random) -> str:
    letters = "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    digits = "".join(rng.choice(string.digits) for _ in range(7))
    return letters + digits


def generate_indian_passport(rng: random.Random) -> str:
    valid_letters = [c for c in string.ascii_uppercase if c not in "QXZ"]
    letter = rng.choice(valid_letters)
    d1 = rng.choice(string.digits[1:])
    d2 = rng.choice(string.digits)
    mid4 = "".join(rng.choice(string.digits) for _ in range(4))
    dlast = rng.choice(string.digits[1:])
    space = rng.choice(("", " "))
    return f"{letter}{d1}{d2}{space}{mid4}{dlast}"


def generate_driving_licence(rng: random.Random) -> str:
    state_code = rng.choice(_RTO_CODES)
    office = f"{rng.randint(1, 99):02d}"
    year = str(rng.randint(1980, 2024))
    serial = "".join(rng.choice(string.digits) for _ in range(7))
    sep = _sep(rng)
    return f"{state_code}{office}{sep}{year}{sep}{serial}"


def generate_vehicle_reg(rng: random.Random) -> str:
    state_code = rng.choice(_RTO_CODES)
    office = str(rng.randint(1, 99))
    series = "".join(rng.choice(string.ascii_uppercase) for _ in range(rng.choice((1, 2))))
    number = "".join(rng.choice(string.digits) for _ in range(4))
    sep = _sep(rng)
    return f"{state_code}{sep}{office}{sep}{series}{sep}{number}"


def generate_abha_number(rng: random.Random) -> str:
    digits = _digits(rng, 14, first="123456789")
    sep = rng.choice((" ", "-"))
    return f"{digits[0:2]}{sep}{digits[2:6]}{sep}{digits[6:10]}{sep}{digits[10:14]}"


def generate_abha_address(rng: random.Random) -> str:
    handle_len = rng.randint(4, 14)
    handle = "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(handle_len))
    domain = rng.choice(("abdm", "sbx"))
    return f"{handle}@{domain}"


def generate_bank_account(rng: random.Random) -> str:
    length = rng.randint(9, 18)
    return _digits(rng, length, first="123456789")


def generate_indian_address(rng: random.Random) -> str:
    unit = rng.choice(_UNIT_MARKERS)
    unit_no = f"{rng.randint(1, 999)}{rng.choice(('', 'A', 'B'))}"
    locality = f"{generate_person_name(rng).split()[0]} {rng.choice(_LOCALITY_SUFFIXES)}"
    city = rng.choice(_CITIES)
    state = rng.choice(_STATES_TITLE)
    return f"{unit} {unit_no}, {locality}, {city}, {state}"
