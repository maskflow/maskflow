"""Registers MaskFlow's original 12 intl/US-shaped recognizers (EMAIL, PHONE,
SSN, CREDIT_CARD, IP_ADDRESS, AWS_KEY, API_KEY, JWT, IBAN, ADDRESS, PERSON_NAME,
DATE_OF_BIRTH) against maskflow-core on import. Importing this package is the
side effect that makes detect()/mask()/unmask() aware of these types -- see
maskflow_core.registry.register_pattern / register_ner_recognizer.
"""

from maskflow_core.registry import register_ner_recognizer, register_pattern

from . import ner, patterns

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

__all__: list[str] = []
