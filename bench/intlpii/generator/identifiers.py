"""One generate_<TYPE>(rng) -> str per registered maskflow-pack-intl label.

Every value returned here is checksum-VALID (CREDIT_CARD / IBAN), drawn
from a real-but-never-assigned range (SSN area, PHONE 555-01xx), or
structurally valid to its documented format (EMAIL, AWS_KEY, API_KEY, JWT,
IP_ADDRESS, ADDRESS, PERSON_NAME, DATE_OF_BIRTH). generate.py's self-check
verifies the checksum-bearing ones against the pack's own validators rather
than trusting this module blindly.

Name / street corpora here are hand-written placeholder data -- not drawn
from any real person or address (CLAUDE.md rule 2), the same discipline
maskflow_pack_intl.surrogates already follows for its own synthetic
corpora.
"""

from __future__ import annotations

import random
import string

# --- synthetic corpora (comment-marked synthetic, CLAUDE.md rule 2) --------

# Deliberately multi-origin so PERSON_NAME recall is measured on more than
# one name morphology, matching the pack's own surrogate corpus spirit.
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
    "Quinn",
    "Rosa",
    "Sven",
    "Tara",
    "Umar",
    "Vera",
    "Wanda",
    "Yusuf",
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
    "Rasmussen",
    "Silva",
    "Tanaka",
    "Vaughn",
    "Whitfield",
    "Yoon",
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
    "Lakeshore",
    "Ironwood",
    "Pinecrest",
)
# Only suffixes ADDRESS_RE accepts (patterns.py: ADDRESS_RE).
_STREET_SUFFIXES = (
    "Street",
    "St",
    "Avenue",
    "Ave",
    "Road",
    "Rd",
    "Boulevard",
    "Blvd",
    "Lane",
    "Ln",
    "Drive",
    "Dr",
    "Court",
    "Ct",
    "Way",
    "Place",
    "Pl",
    "Terrace",
    "Ter",
)
_SECONDARY_UNIT = ("Apt", "Suite", "Ste", "Unit")

# IBAN country codes with their total IBAN length (ISO 13616 registry).
_IBAN_SPECS = {
    "GB": 22,
    "DE": 22,
    "FR": 27,
    "ES": 24,
    "NL": 18,
    "IE": 22,
    "IT": 27,
}

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _digits(rng: random.Random, n: int, *, first: str = "0123456789") -> str:
    return rng.choice(first) + "".join(rng.choice(string.digits) for _ in range(n - 1))


# --- checksum helpers (kept local so the generator is self-contained; the
#     pack's validators are what generate.py's self-check trusts) -----------


def _luhn_check_digit(body: str) -> str:
    """Return the digit that makes `body + digit` pass the Luhn check --
    the same algorithm maskflow_pack_intl.patterns.luhn_is_valid verifies."""
    total = 0
    # `body` will be followed by one more digit, so the rightmost body digit
    # sits at an even distance-from-end -> doubled.
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def _iban_check_digits(country: str, bban: str) -> str:
    """mod-97 check digits, matching patterns.iban_is_valid's math."""
    rearranged = bban + country + "00"
    converted = "".join(str(int(c, 36)) for c in rearranged)
    return f"{98 - int(converted) % 97:02d}"


# --- generators -----------------------------------------------------------


def generate_person_name(rng: random.Random) -> str:
    return f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"


def generate_email(rng: random.Random) -> str:
    first = rng.choice(_FIRST_NAMES).lower()
    last = rng.choice(_LAST_NAMES).lower()
    sep = rng.choice((".", "_", ""))
    tag = rng.choice(("", "", f"{rng.randint(1, 99)}"))
    # Non-reserved-looking domains: this is detection input, not a surrogate,
    # so it should look like ordinary mail (the pack's SURROGATE path is what
    # uses example.com). Still fully synthetic company words.
    domain = rng.choice(
        (
            "northwind-traders.com",
            "contoso.co",
            "acme-logistics.net",
            "brightmail.io",
            "cascade-health.org",
            "meridianbank.com",
        )
    )
    return f"{first}{sep}{last}{tag}@{domain}"


def generate_phone(rng: random.Random) -> str:
    """NANP-shaped, 555-01xx subscriber range (reserved for fiction). Format
    always matches PHONE_RE (needs a separator between the last three
    groups)."""
    area = f"{rng.randint(2, 9)}{rng.randint(0, 9)}{rng.randint(0, 9)}"
    subscriber = f"01{rng.randint(0, 99):02d}"
    style = rng.choice(("dash", "dot", "paren", "intl"))
    if style == "dash":
        return f"{area}-555-{subscriber}"
    if style == "dot":
        return f"{area}.555.{subscriber}"
    if style == "paren":
        return f"({area}) 555-{subscriber}"
    return f"+1 {area} 555 {subscriber}"


def generate_ssn(rng: random.Random) -> str:
    """Dashed SSN with a structurally valid area number (not 000/666/9xx)."""
    area = rng.randint(1, 899)
    while area == 666:
        area = rng.randint(1, 899)
    group = rng.randint(1, 99)
    serial = rng.randint(1, 9999)
    return f"{area:03d}-{group:02d}-{serial:04d}"


def generate_ssn_plain(rng: random.Random) -> str:
    """Bare 9-digit SSN (only detected with an 'ssn'/'social security'
    keyword nearby -- templates supply that context)."""
    return generate_ssn(rng).replace("-", "")


def generate_credit_card(rng: random.Random) -> str:
    """Luhn-valid 16-digit PAN with a plausible major-industry prefix.
    Prefix digits are real IIN ranges; everything after is random, so the
    number as a whole is never a real issued card."""
    prefix = rng.choice(("4", "51", "52", "53", "54", "55", "37", "6011"))
    body_len = 15 - len(prefix)
    body = prefix + "".join(rng.choice(string.digits) for _ in range(body_len))
    full = body + _luhn_check_digit(body)
    style = rng.choice(("plain", "spaced", "dashed"))
    if style == "spaced":
        return " ".join(full[i : i + 4] for i in range(0, len(full), 4))
    if style == "dashed":
        return "-".join(full[i : i + 4] for i in range(0, len(full), 4))
    return full


def generate_ip_address(rng: random.Random) -> str:
    if rng.random() < 0.85:
        return ".".join(str(rng.randint(1, 254)) for _ in range(4))
    return ":".join(f"{rng.randint(0, 0xFFFF):x}" for _ in range(8))


def generate_aws_key(rng: random.Random) -> str:
    prefix = rng.choice(("AKIA", "ASIA"))
    return prefix + "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(16))


def generate_api_key(rng: random.Random) -> str:
    # No Slack-style (xoxb-...) token here on purpose: a random one still
    # matches GitHub's push-protection secret scanner closely enough to
    # block the corpus, even though it is pure noise. The pack's API_KEY_RE
    # still covers the xox* branch; this benchmark just doesn't exercise it.
    style = rng.choice(("openai", "anthropic", "github", "google"))
    alnum = string.ascii_letters + string.digits
    if style == "openai":
        return "sk-" + "".join(rng.choice(alnum + "_-") for _ in range(40))
    if style == "anthropic":
        return "sk-ant-" + "".join(rng.choice(alnum + "_-") for _ in range(40))
    if style == "github":
        return rng.choice(("ghp_", "gho_", "ghu_")) + "".join(rng.choice(alnum) for _ in range(36))
    return "AIza" + "".join(rng.choice(alnum + "_-") for _ in range(35))


def generate_jwt(rng: random.Random) -> str:
    alnum = string.ascii_letters + string.digits + "_-"
    header = "eyJ" + "".join(rng.choice(alnum) for _ in range(rng.randint(20, 30)))
    payload = "eyJ" + "".join(rng.choice(alnum) for _ in range(rng.randint(40, 90)))
    sig = "".join(rng.choice(alnum) for _ in range(rng.randint(30, 43)))
    return f"{header}.{payload}.{sig}"


def generate_iban(rng: random.Random) -> str:
    country, total_len = rng.choice(list(_IBAN_SPECS.items()))
    bban_len = total_len - 4
    bban = "".join(rng.choice(string.digits) for _ in range(bban_len))
    return f"{country}{_iban_check_digits(country, bban)}{bban}"


def generate_address(rng: random.Random) -> str:
    number = rng.randint(1, 9999)
    name = rng.choice(_STREET_NAMES)
    suffix = rng.choice(_STREET_SUFFIXES)
    base = f"{number} {name} {suffix}"
    if rng.random() < 0.3:
        unit = rng.choice(_SECONDARY_UNIT)
        base += f", {unit} {rng.randint(1, 40)}{rng.choice(('', 'A', 'B'))}"
    return base


def generate_date_of_birth(rng: random.Random) -> str:
    year = rng.randint(1955, 2004)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    style = rng.choice(("slash", "dash", "long"))
    if style == "slash":
        return f"{month:02d}/{day:02d}/{year}"
    if style == "dash":
        return f"{year}-{month:02d}-{day:02d}"
    return f"{_MONTHS[month - 1]} {day}, {year}"
