"""Strategy.SURROGATE fake-value generators for the intl pack's types --
each documented with the reserved/invalid range or corpus it draws from, so
a value never collides with something a real issuer could plausibly assign.
maskflow-core falls back to Strategy.REPLACE for any type with no generator
here (AWS_KEY, API_KEY, JWT, IP_ADDRESS, DATE_OF_BIRTH -- see __init__.py's
registration comments for why each is skipped).

All corpora below (names, streets) are hand-written placeholder data, not
drawn from any real person or address -- same "comment-marked synthetic"
discipline CLAUDE.md rule 2 asks of test fixtures.
"""

from __future__ import annotations

import random
import re

# Synthetic first/last names -- not real people, used only to build
# plausible-looking PERSON_NAME/EMAIL surrogates.
_FIRST_NAMES = (
    "Aiden",
    "Bianca",
    "Carlos",
    "Dana",
    "Ethan",
    "Farah",
    "Gavin",
    "Hana",
    "Ivan",
    "Jolene",
    "Kiran",
    "Lena",
    "Mateo",
    "Nadia",
    "Omar",
    "Priya",
)
_LAST_NAMES = (
    "Alvarez",
    "Brennan",
    "Castillo",
    "Dupont",
    "Ellison",
    "Farooqi",
    "Goldberg",
    "Huang",
    "Ibarra",
    "Jansen",
    "Kowalski",
    "Lindqvist",
    "Mercer",
    "Nakamura",
    "Okafor",
    "Petrova",
)
_STREET_NAMES = (
    "Maple",
    "Cedar",
    "Birch",
    "Fairview",
    "Sunset",
    "Harbor",
    "Willow",
    "Meridian",
    "Foxglove",
    "Hollow",
)
_STREET_SUFFIXES = ("Street", "Avenue", "Road", "Lane", "Drive", "Court", "Way")

_DIGIT_RE = re.compile(r"\d")

# Publicly documented Luhn-valid test card numbers used industry-wide by
# payment processors' sandboxes (Visa/Mastercard/Amex/Discover) -- never
# issued to a real cardholder. https://stripe.com/docs/testing publishes the
# same list.
_TEST_CARD_NUMBERS = (
    "4242424242424242",  # Visa
    "4000056655665556",  # Visa (debit)
    "5555555555554444",  # Mastercard
    "378282246310005",  # American Express
    "6011111111111117",  # Discover
    "3056930009020004",  # Diners Club
)


def _fill_digits(original: str, digits: str, rng: random.Random) -> str:
    """Splice `digits` into `original`'s non-digit skeleton, right-aligned
    (so a preserved country-code/leading-digit prefix stays leftmost and the
    reserved suffix -- e.g. SSN's serial, phone's 555-01XX -- lands where it
    should). Extra leading digit slots beyond len(digits) get random filler."""
    positions = [m.start() for m in _DIGIT_RE.finditer(original)]
    chars = list(original)
    pad = len(positions) - len(digits)
    filler = "".join(str(rng.randint(1, 9)) for _ in range(max(0, pad)))
    full = (filler + digits)[-len(positions) :] if pad > 0 else digits[-len(positions) :]
    # strict=True: `full` is sliced to exactly len(positions) characters
    # above -- a length mismatch here would mean that invariant broke.
    for i, ch in zip(positions, full, strict=True):
        chars[i] = ch
    return "".join(chars)


def email_surrogate(_original: str, rng: random.Random) -> str:
    """RFC 2606 reserved domains (example.com/.org/.net) -- guaranteed
    non-deliverable, never assignable to a real mailbox."""
    local = f"{rng.choice(_FIRST_NAMES)}.{rng.choice(_LAST_NAMES)}{rng.randint(10, 99)}".lower()
    domain = rng.choice(("example.com", "example.org", "example.net"))
    return f"{local}@{domain}"


def phone_surrogate(original: str, rng: random.Random) -> str:
    """NANP fictional range: exchange 555, subscriber 0100-0199 -- reserved
    by the North American Numbering Plan for fiction/testing, never assigned
    to a real subscriber. Area code is any plausible (2-9 leading) digit
    string, since only the 555-01XX suffix is actually reserved."""
    area = f"{rng.randint(2, 9)}{rng.randint(0, 9)}{rng.randint(0, 9)}"
    subscriber = f"01{rng.randint(0, 99):02d}"
    return _fill_digits(original, f"{area}555{subscriber}", rng)


def ssn_surrogate(original: str, rng: random.Random) -> str:
    """SSA-reserved-invalid area range 900-999 -- the SSA has stated it will
    never assign an area number in this range, so no real SSN can collide."""
    area = str(rng.randint(900, 999))
    group = f"{rng.randint(1, 99):02d}"
    serial = f"{rng.randint(1, 9999):04d}"
    return _fill_digits(original, f"{area}{group}{serial}", rng)


def credit_card_surrogate(_original: str, rng: random.Random) -> str:
    """Publicly documented payment-industry test numbers (see
    _TEST_CARD_NUMBERS) -- Luhn-valid, never issued to a real cardholder."""
    return rng.choice(_TEST_CARD_NUMBERS)


def _iban_check_digits(country: str, bban: str) -> str:
    rearranged = bban + country + "00"
    converted = "".join(str(int(c, 36)) for c in rearranged)
    remainder = int(converted) % 97
    return f"{98 - remainder:02d}"


def iban_surrogate(original: str, rng: random.Random) -> str:
    """Keeps the original's country code (so it still looks like the same
    country) but a bank/branch code starting with an obviously-synthetic "9"
    digit no real issuer's code starts with, with correctly computed mod-97
    check digits so it still passes structural validation -- checksum-valid
    but from a bank code no real issuer uses."""
    country = original[:2].upper() if len(original) >= 2 and original[:2].isalpha() else "GB"
    bban_length = max(11, len(original) - 4)
    bban = "9" + "".join(str(rng.randint(0, 9)) for _ in range(bban_length - 1))
    check_digits = _iban_check_digits(country, bban)
    return f"{country}{check_digits}{bban}"


def person_name_surrogate(_original: str, rng: random.Random) -> str:
    return f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"


def address_surrogate(_original: str, rng: random.Random) -> str:
    number = rng.randint(100, 9999)
    return f"{number} {rng.choice(_STREET_NAMES)} {rng.choice(_STREET_SUFFIXES)}"
