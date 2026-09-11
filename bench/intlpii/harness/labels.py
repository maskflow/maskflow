"""Canonical entity taxonomy (the intl corpus's own positive labels) and
each adapter's raw-label -> canonical-label map.

The taxonomy is never invented here -- it is whatever `value_class:
"positive"` labels appear in the loaded corpus (see
maskflow_bench.labels.canonical_labels, reused directly).

Every map below is intentionally partial: a raw label an adapter emits
with no entry here is dropped before scoring, never counted as a false
positive against an unrelated canonical type (see
maskflow_bench.matching).

Two mappings are deliberately *generous* and cost the mapped adapter some
precision on this corpus, exactly as maskflow_bench.labels already
does for `PHONE_NUMBER -> INDIAN_MOBILE`:

- `DATE_TIME -> DATE_OF_BIRTH`: Presidio/mask-privacy tag every date, not
  just birth dates. Mapping it is the fairest way to give them *any* recall
  on DATE_OF_BIRTH; the price is a false positive on every non-DOB date.
- `LOCATION -> ADDRESS`: same trade -- a spaCy GPE/LOC is not a street
  address, but it is the nearest thing these engines emit.

The published table shows both, and the README calls out which rows carry
this caveat.
"""

from __future__ import annotations

from collections.abc import Iterable

# Re-exported so callers can `from bench.intlpii.harness.labels import
# canonical_labels` without caring that the implementation is shared.
from maskflow_bench.labels import canonical_labels, identity_map

__all__ = [
    "LABEL_DESCRIPTIONS",
    "MASK_PRIVACY_LABEL_MAP",
    "NAIVE_REGEX_LABEL_MAP",
    "PRESIDIO_LABEL_MAP",
    "canonical_labels",
    "identity_map",
]

# Human-readable glosses for the LLM adapter's prompt. The taxonomy itself
# always comes from canonical_labels(docs); this is just documentation.
LABEL_DESCRIPTIONS: dict[str, str] = {
    "EMAIL": "an email address",
    "PHONE": "a phone number (NANP-style, 7-11 digits, optionally +country prefix)",
    "SSN": "a US Social Security Number, 9 digits, often written AAA-GG-SSSS",
    "CREDIT_CARD": "a payment card number, 13-19 digits, Luhn-valid, may be spaced/hyphenated",
    "IP_ADDRESS": "an IPv4 or IPv6 address",
    "AWS_KEY": "an AWS access key id (starts AKIA or ASIA, then 16 upper-case alphanumerics)",
    "API_KEY": "an API key or secret token (e.g. sk-..., sk-ant-..., ghp_..., xoxb-..., AIza...)",
    "JWT": "a JSON Web Token: three base64url segments separated by dots, starts eyJ",
    "IBAN": "an International Bank Account Number (2-letter country + 2 check digits + BBAN)",
    "ADDRESS": "a street address (number + street name + Street/Ave/Road/... + optional unit)",
    "PERSON_NAME": "a person's name",
    "DATE_OF_BIRTH": "a date of birth specifically (not an arbitrary date)",
}

# Presidio predefined recognizers, out of the box. AWS_KEY / API_KEY / JWT
# have no Presidio equivalent -> 0 recall there is expected, not a bug.
PRESIDIO_LABEL_MAP: dict[str, str] = {
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "CREDIT_CARD": "CREDIT_CARD",
    "IP_ADDRESS": "IP_ADDRESS",
    "IBAN_CODE": "IBAN",
    "PERSON": "PERSON_NAME",
    "US_SSN": "SSN",
    "DATE_TIME": "DATE_OF_BIRTH",  # generous -- see module docstring
    "LOCATION": "ADDRESS",  # generous -- see module docstring
}

# mask-privacy's DLP registry + its Presidio-backed NLP tier. Raw type
# names verified against the installed package (mask-privacy 4.3.0) -- see
# harness/tests/test_harness_intl.py's note. mask-privacy at its defaults
# emits nothing for SSN / AWS_KEY / API_KEY / JWT on this corpus; 0 recall
# on those rows is the measured result, not a mapping omission.
MASK_PRIVACY_LABEL_MAP: dict[str, str] = {
    "EMAIL_ADDR": "EMAIL",
    "PHONE_NUM": "PHONE",
    "PHONE_NUM_INTL": "PHONE",
    "US_SSN": "SSN",
    "CREDIT_CARD_NUMBER": "CREDIT_CARD",
    "IPV4_ADDR": "IP_ADDRESS",
    "IPV6_ADDR": "IP_ADDRESS",
    "INTL_BANK_IBAN": "IBAN",
    "PERSON": "PERSON_NAME",
    "BIRTH_DATE": "DATE_OF_BIRTH",
    "DATE_TIME": "DATE_OF_BIRTH",  # generous -- see module docstring
    "PHYS_ADDRESS": "ADDRESS",
    "LOCATION": "ADDRESS",  # generous -- see module docstring
}

# The intl naive-regex adapter's own made-up label names -> canonical.
NAIVE_REGEX_LABEL_MAP: dict[str, str] = {
    "EMAIL_SHAPED": "EMAIL",
    "PHONE_SHAPED": "PHONE",
    "SSN_SHAPED": "SSN",
    "CARD_SHAPED": "CREDIT_CARD",
    "IPV4_SHAPED": "IP_ADDRESS",
    "AWS_KEY_SHAPED": "AWS_KEY",
    "JWT_SHAPED": "JWT",
}


def describe(labels: Iterable[str]) -> dict[str, str]:
    """LABEL_DESCRIPTIONS restricted to `labels` (the corpus taxonomy),
    for callers that want to be sure they only prompt with real types."""
    return {label: LABEL_DESCRIPTIONS.get(label, "") for label in labels}
