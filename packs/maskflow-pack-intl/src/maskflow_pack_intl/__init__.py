"""Registers MaskFlow's original 12 intl/US-shaped recognizers (EMAIL, PHONE,
SSN, CREDIT_CARD, IP_ADDRESS, AWS_KEY, API_KEY, JWT, IBAN, ADDRESS, PERSON_NAME,
DATE_OF_BIRTH) against maskflow-core on import. Importing this package is the
side effect that makes detect()/mask()/unmask() aware of these types.

Each recognizer below is a declarative Recognizer object (see
maskflow_core.recognizer -- issue #21's pluggable interface) rather than a
bare register_pattern()/register_ner_recognizer() call; `_add()` both
registers it immediately (so the existing import-time side effect this
pack's callers rely on is unchanged) and keeps it in `_RECOGNIZERS`, which
`load_recognizers()` exposes as this pack's "maskflow.recognizers"
entry-point target (see pyproject.toml) for RecognizerRegistry-based
discovery. Recognizer.register() is idempotent per instance, so a process
that uses both the import-time path and RecognizerRegistry-based discovery
for this pack registers each pattern once, not twice.
"""

from maskflow_core.entities import PIIType
from maskflow_core.recognizer import NlpRecognizer, PatternRecognizer, Recognizer
from maskflow_core.registry import register_surrogate_generator

from . import ner, patterns, surrogates

_RECOGNIZERS: list[Recognizer] = []


def _add(recognizer: Recognizer) -> PIIType:
    """Keep `recognizer` for load_recognizers()'s entry-point target, and
    register it now for this module's own import-time side effect. Returns
    the registered PIIType, like register_pattern()/register_ner_recognizer()
    used to, for any call site that needs it."""
    _RECOGNIZERS.append(recognizer)
    return recognizer.register()


_add(PatternRecognizer("EMAIL", patterns.EMAIL_RE, 0.95))

_add(
    PatternRecognizer(
        "PHONE",
        patterns.PHONE_RE,
        0.85,
        context_keywords=("phone", "call", "tel", "mobile", "cell", "contact"),
    )
)

_add(
    PatternRecognizer(
        "SSN",
        patterns.SSN_DASHED_RE,
        0.95,
        validator=patterns.validate_ssn_dashed,
        context_keywords=("ssn", "social security"),
    )
)
_add(
    PatternRecognizer(
        "SSN",
        patterns.SSN_PLAIN_RE,
        0.35,
        validator=patterns.validate_ssn_plain,
        context_keywords=("ssn", "social security"),
    )
)

_add(
    PatternRecognizer(
        "CREDIT_CARD",
        patterns.CREDIT_CARD_RE,
        0.9,
        validator=patterns.validate_credit_card,
        context_keywords=("card number", "credit card", "visa", "mastercard", "cc#"),
    )
)

_add(PatternRecognizer("IP_ADDRESS", patterns.IPV4_RE, 0.75))
_add(PatternRecognizer("IP_ADDRESS", patterns.IPV6_RE, 0.85))

_add(PatternRecognizer("AWS_KEY", patterns.AWS_KEY_RE, 0.97))

_add(
    PatternRecognizer(
        "API_KEY",
        patterns.API_KEY_RE,
        0.95,
        context_keywords=("api key", "apikey", "secret", "token", "credential"),
    )
)
_add(
    PatternRecognizer(
        "API_KEY",
        patterns.GENERIC_SECRET_ASSIGNMENT_RE,
        0.6,
        context_keywords=("api key", "apikey", "secret", "token", "credential"),
    )
)

_add(PatternRecognizer("JWT", patterns.JWT_RE, 0.9))

_add(PatternRecognizer("IBAN", patterns.IBAN_RE, 0.6, validator=patterns.validate_iban))

_add(
    PatternRecognizer(
        "ADDRESS",
        patterns.ADDRESS_RE,
        0.7,
        context_keywords=("address", "lives at", "located at", "ship to", "mailing"),
    )
)

_add(
    NlpRecognizer(
        "PERSON",
        "PERSON_NAME",
        ner.PERSON_BASE_CONFIDENCE,
        context_keywords=("name is", "name:", "my name", "signed", "regards"),
    )
)
_add(
    NlpRecognizer(
        "DATE",
        "DATE_OF_BIRTH",
        ner.DATE_BASE_CONFIDENCE,
        threshold=ner.DATE_OF_BIRTH_THRESHOLD,
        context_keywords=("dob", "date of birth", "born on", "birthdate"),
    )
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


def load_recognizers() -> list[Recognizer]:
    """Entry-point target for RecognizerRegistry-based discovery (group
    "maskflow.recognizers", see pyproject.toml) -- returns the same
    Recognizer objects already registered above by importing this module.
    Loading this entry point necessarily imports this module (Python import
    semantics), which has already run every _add() call above by the time
    this function is reachable -- RecognizerRegistry.register_all() calling
    .register() on these same objects again is safe: Recognizer.register()
    is idempotent per instance (see maskflow_core.recognizer)."""
    return list(_RECOGNIZERS)


__all__: list[str] = ["load_recognizers"]
