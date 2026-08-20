"""Registers MaskFlow's original 12 intl/US-shaped recognizers (EMAIL, PHONE,
SSN, CREDIT_CARD, IP_ADDRESS, AWS_KEY, API_KEY, JWT, IBAN, ADDRESS, PERSON_NAME,
DATE_OF_BIRTH) against maskflow-core on import. Importing this package is the
side effect that makes detect()/mask()/unmask() aware of these types -- see
maskflow_core.registry.register_pattern / register_ner_recognizer.
"""

from maskflow_core.registry import (
    register_ner_recognizer,
    register_pattern,
    register_surrogate_generator,
)

from . import ner, patterns, surrogates

register_pattern("EMAIL", patterns.EMAIL_RE, 0.95)

register_pattern(
    "PHONE",
    patterns.PHONE_RE,
    0.85,
    context_keywords=("phone", "call", "tel", "mobile", "cell", "contact"),
)

register_pattern(
    "SSN",
    patterns.SSN_DASHED_RE,
    0.95,
    validator=patterns.validate_ssn_dashed,
    context_keywords=("ssn", "social security"),
)
register_pattern(
    "SSN",
    patterns.SSN_PLAIN_RE,
    0.35,
    validator=patterns.validate_ssn_plain,
    context_keywords=("ssn", "social security"),
)

register_pattern(
    "CREDIT_CARD",
    patterns.CREDIT_CARD_RE,
    0.9,
    validator=patterns.validate_credit_card,
    context_keywords=("card number", "credit card", "visa", "mastercard", "cc#"),
)

register_pattern("IP_ADDRESS", patterns.IPV4_RE, 0.75)
register_pattern("IP_ADDRESS", patterns.IPV6_RE, 0.85)

register_pattern("AWS_KEY", patterns.AWS_KEY_RE, 0.97)

register_pattern(
    "API_KEY",
    patterns.API_KEY_RE,
    0.95,
    context_keywords=("api key", "apikey", "secret", "token", "credential"),
)
register_pattern(
    "API_KEY",
    patterns.GENERIC_SECRET_ASSIGNMENT_RE,
    0.6,
    context_keywords=("api key", "apikey", "secret", "token", "credential"),
)

register_pattern("JWT", patterns.JWT_RE, 0.9)

register_pattern("IBAN", patterns.IBAN_RE, 0.6, validator=patterns.validate_iban)

register_pattern(
    "ADDRESS",
    patterns.ADDRESS_RE,
    0.7,
    context_keywords=("address", "lives at", "located at", "ship to", "mailing"),
)

register_ner_recognizer(
    "PERSON",
    "PERSON_NAME",
    ner.PERSON_BASE_CONFIDENCE,
    context_keywords=("name is", "name:", "my name", "signed", "regards"),
)
register_ner_recognizer(
    "DATE",
    "DATE_OF_BIRTH",
    ner.DATE_BASE_CONFIDENCE,
    threshold=ner.DATE_OF_BIRTH_THRESHOLD,
    context_keywords=("dob", "date of birth", "born on", "birthdate"),
)

# Strategy.SURROGATE fake-value generators -- see surrogates.py for the
# reserved/invalid range or corpus each one draws from. AWS_KEY, API_KEY,
# JWT, and IP_ADDRESS have no bespoke generator: there's no meaningful
# "plausible fake" concept for an opaque secret, and a fake IP is no safer
# to fabricate than a real one might be misleading -- SURROGATE falls back
# to REPLACE for these. DATE_OF_BIRTH is skipped too: input date formats
# vary too widely (spaCy NER, not a fixed regex) to fake safely in the same
# shape as the original without a date-parsing dependency.
register_surrogate_generator(
    "EMAIL", surrogates.email_surrogate, "RFC 2606 reserved example.com/.org/.net domains"
)
register_surrogate_generator(
    "PHONE", surrogates.phone_surrogate, "NANP fictional range: exchange 555, subscriber 0100-0199"
)
register_surrogate_generator(
    "SSN", surrogates.ssn_surrogate, "SSA-reserved-invalid area numbers 900-999"
)
register_surrogate_generator(
    "CREDIT_CARD",
    surrogates.credit_card_surrogate,
    "publicly documented payment-industry test numbers (Stripe/Visa/Mastercard/Amex)",
)
register_surrogate_generator(
    "IBAN", surrogates.iban_surrogate, "mod-97-valid with a synthetic '9'-prefixed bank code"
)
register_surrogate_generator(
    "PERSON_NAME", surrogates.person_name_surrogate, "embedded synthetic first/last name corpus"
)
register_surrogate_generator(
    "ADDRESS", surrogates.address_surrogate, "embedded synthetic street name corpus"
)

__all__: list[str] = []
