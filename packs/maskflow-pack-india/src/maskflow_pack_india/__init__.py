"""Registers MaskFlow's India-specific recognizers (AADHAAR, AADHAAR_MASKED,
PAN, GSTIN, IFSC, UPI_VPA, INDIAN_MOBILE, PIN_CODE, VOTER_ID,
INDIAN_PASSPORT, DRIVING_LICENCE, VEHICLE_REG, ABHA_NUMBER, ABHA_ADDRESS,
BANK_ACCOUNT_IN, PERSON_NAME, INDIAN_ADDRESS) against maskflow-core on
import. Importing this package is the side effect that makes
detect()/mask()/unmask() aware of these types.

Context keywords are positive-only (English, Hindi/Devanagari, and Hinglish
transliterations) -- maskflow-core's context.apply_context_boost() has no
negative-context mechanism yet (CLAUDE.md's confidence formula documents one
as a target, but it isn't implemented in core), so "example/test/dummy"-style
suppression is out of scope for this pack until core grows that hook.

Each recognizer below is a declarative Recognizer object (see
maskflow_core.recognizer -- issue #21's pluggable interface) rather than a
bare register_pattern()/register_custom_recognizer()/register_ner_recognizer()
call; `_add()` both registers it immediately (so the existing import-time
side effect this pack's callers rely on is unchanged) and keeps it in
`_RECOGNIZERS`, which `load_recognizers()` exposes as this pack's
"maskflow.recognizers" entry-point target (see pyproject.toml) for
RecognizerRegistry-based discovery. Recognizer.register() is idempotent per
instance, so a process that uses both the import-time path and
RecognizerRegistry-based discovery for this pack registers each pattern
once, not twice.
"""

from maskflow_core.context import CONTEXT_KEYWORDS
from maskflow_core.entities import PIIType
from maskflow_core.recognizer import (
    GazetteerRecognizer,
    NlpRecognizer,
    PatternRecognizer,
    Recognizer,
)
from maskflow_core.registry import register_surrogate_generator

from . import gazetteer, patterns, surrogates
from .data.indian_places import INDIAN_STATE_UT_NAMES

_RECOGNIZERS: list[Recognizer] = []


def _add(recognizer: Recognizer) -> PIIType:
    """Keep `recognizer` for load_recognizers()'s entry-point target, and
    register it now for this module's own import-time side effect. Returns
    the registered PIIType, like register_pattern()/register_custom_recognizer()
    used to, for any call site that needs it."""
    _RECOGNIZERS.append(recognizer)
    return recognizer.register()


_add(
    PatternRecognizer(
        "AADHAAR",
        patterns.AADHAAR_RE,
        0.5,
        validator=patterns.validate_aadhaar,
        context_keywords=(
            "aadhaar",
            "aadhar",
            "adhaar",
            "uidai",
            "aadhaar number",
            "aadhaar no",
            "aadhar no",
            "aadhaar card",
            "uid number",
            "आधार",
            "आधार कार्ड",
            "आधार संख्या",
        ),
    )
)
_add(
    PatternRecognizer(
        "AADHAAR",
        patterns.AADHAAR_VID_RE,
        0.5,
        validator=patterns.validate_aadhaar,
        context_keywords=(
            "vid",
            "virtual id",
            "aadhaar vid",
            "aadhaar",
            "aadhar",
            "uidai",
            "आधार",
            "वर्चुअल आईडी",
        ),
    )
)
_add(
    PatternRecognizer(
        "AADHAAR_MASKED",
        patterns.AADHAAR_MASKED_RE,
        # No validator possible (8 of 12 digits are gone) -- 0.45 starts BELOW
        # detection.py's DEFAULT_MIN_CONFIDENCE (0.5), same design as pack-intl's
        # SSN_PLAIN: an unvalidated, structurally-ambiguous match should need a
        # nearby keyword to clear the bar, not pass on shape alone.
        0.45,
        context_keywords=(
            "aadhaar",
            "aadhar",
            "adhaar",
            "uidai",
            "masked aadhaar",
            "aadhaar ending",
            "आधार",
        ),
    )
)

_add(
    PatternRecognizer(
        "PAN",
        patterns.PAN_RE,
        0.6,
        validator=patterns.validate_pan,
        context_keywords=(
            "pan",
            "pan card",
            "pan number",
            "pan no",
            "permanent account number",
            "पैन",
            "पैन कार्ड",
            "पैन नंबर",
        ),
    )
)
_add(
    PatternRecognizer(
        "PAN", patterns.PAN_EMBEDDED_IN_GSTIN_RE, 0.6, validator=patterns.validate_pan
    )
)

_add(
    PatternRecognizer(
        "GSTIN",
        patterns.GSTIN_RE,
        0.6,
        validator=patterns.validate_gstin,
        context_keywords=(
            "gstin",
            "gst number",
            "gst no",
            "gst reg",
            "goods and services tax",
            "gstin number",
            "जीएसटी",
            "जीएसटीआईएन",
            "जीएसटी नंबर",
        ),
    )
)

_add(
    PatternRecognizer(
        "IFSC",
        patterns.IFSC_RE,
        0.6,
        validator=patterns.validate_ifsc,
        context_keywords=(
            "ifsc",
            "ifsc code",
            "branch code",
            "bank branch",
            "आईएफएससी",
            "आईएफएससी कोड",
        ),
    )
)

_add(
    PatternRecognizer(
        "UPI_VPA",
        patterns.UPI_VPA_RE,
        0.5,
        validator=patterns.validate_upi_vpa,
        context_keywords=(
            "upi",
            "upi id",
            "vpa",
            "pay to",
            "gpay",
            "google pay",
            "phonepe",
            "paytm",
            "यूपीआई",
            "यूपीआई आईडी",
        ),
    )
)

_add(
    PatternRecognizer(
        "INDIAN_MOBILE",
        patterns.INDIAN_MOBILE_RE,
        0.35,
        validator=patterns.validate_indian_mobile,
        context_keywords=(
            "mobile",
            "mobile number",
            "mobile no",
            "phone",
            "phone number",
            "cell",
            "cell number",
            "contact number",
            "whatsapp",
            "call me at",
            "मोबाइल",
            "मोबाइल नंबर",
            "फ़ोन नंबर",
            "संपर्क नंबर",
        ),
    )
)

# All 28 states + 8 union territories -- a state/UT name next to a 6-digit
# number is as strong a signal for PIN_CODE as the word "pincode" itself.
# (INDIAN_STATE_UT_NAMES now lives in data/indian_places.py, shared with
# INDIAN_ADDRESS's L1 gazetteer -- see gazetteer.py.)

_add(
    PatternRecognizer(
        "PIN_CODE",
        patterns.PIN_CODE_RE,
        0.3,
        context_keywords=(
            "pin",
            "pincode",
            "pin code",
            "postal code",
            "zip",
            "address",
            "district",
            "city",
            "पिन कोड",
            "पिनकोड",
            "डाक कोड",
            # L2 "STRONG mutual PIN_CODE reinforcement" -- the reverse direction
            # of gazetteer.match_indian_places's PIN-proximity boost: a locality
            # suffix word nearby is as strong a PIN_CODE signal as a state name.
            "nagar",
            "colony",
            "vihar",
            "puram",
            "layout",
            "extension",
            "marg",
        )
        + INDIAN_STATE_UT_NAMES,
    )
)

_add(
    PatternRecognizer(
        "VOTER_ID",
        patterns.VOTER_ID_RE,
        0.55,
        context_keywords=(
            "voter id",
            "voter id card",
            "epic",
            "epic no",
            "epic number",
            "electoral roll",
            "election card",
            "मतदाता पहचान पत्र",
            "वोटर आईडी",
        ),
    )
)

_add(
    PatternRecognizer(
        "INDIAN_PASSPORT",
        patterns.INDIAN_PASSPORT_RE,
        0.6,
        context_keywords=(
            "passport",
            "passport no",
            "passport number",
            "पासपोर्ट",
            "पासपोर्ट नंबर",
        ),
    )
)
# No context_keywords here -- register_pattern() stores CONTEXT_KEYWORDS per
# PIIType, not per pattern, so a second non-empty tuple for INDIAN_PASSPORT
# would overwrite the inline registration's keywords above. Doesn't matter
# for the MRZ block anyway: four independent ICAO check digits (0.97) clear
# DEFAULT_MIN_CONFIDENCE on their own, same as GSTIN needing none.
_add(
    PatternRecognizer(
        "INDIAN_PASSPORT",
        patterns.INDIAN_PASSPORT_MRZ_RE,
        0.6,
        validator=patterns.validate_indian_passport_mrz,
    )
)

_add(
    PatternRecognizer(
        "DRIVING_LICENCE",
        patterns.DRIVING_LICENCE_RE,
        0.5,
        validator=patterns.validate_driving_licence,
        context_keywords=(
            "driving licence",
            "driving license",
            "dl no",
            "dl number",
            "licence number",
            "license number",
            "ड्राइविंग लाइसेंस",
            "लाइसेंस नंबर",
        ),
    )
)

_add(
    PatternRecognizer(
        "VEHICLE_REG",
        patterns.VEHICLE_REG_RE,
        0.5,
        validator=patterns.validate_vehicle_reg,
        context_keywords=(
            "vehicle number",
            "vehicle registration",
            "reg no",
            "registration number",
            "vehicle no",
            "car number",
            "गाड़ी नंबर",
            "वाहन पंजीकरण",
        ),
    )
)

_add(
    PatternRecognizer(
        "ABHA_NUMBER",
        patterns.ABHA_NUMBER_RE,
        0.35,
        context_keywords=(
            "abha",
            "abha number",
            "abha id",
            "health id",
            "abdm",
            "ayushman",
            "ayushman bharat",
            "national health id",
            "आभा",
            "आभा नंबर",
            "स्वास्थ्य आईडी",
            "आयुष्मान",
        ),
    )
)

_add(
    PatternRecognizer(
        "ABHA_ADDRESS",
        patterns.ABHA_ADDRESS_RE,
        0.5,
        validator=patterns.validate_abha_address,
        context_keywords=(
            "abha address",
            "abha id",
            "health id",
            "abdm",
            "आभा पता",
            "आभा आईडी",
        ),
    )
)

_add(
    PatternRecognizer(
        "BANK_ACCOUNT_IN",
        patterns.BANK_ACCOUNT_IN_RE,
        0.3,
        context_keywords=(
            "account",
            "account no",
            "account number",
            "a/c",
            "a/c no",
            "acct",
            "acct no",
            "bank account",
            "खाता संख्या",
            "खाता नंबर",
            "बैंक खाता",
        ),
    )
)

# ---------------------------------------------------------------------------
# PERSON_NAME (Indian) -- L1 Gazetteer (below) + L2 Structural (honorifics/
# relational-marker/initials/form-field patterns, registered further down
# after INDIAN_ADDRESS's L1). spaCy NLP agreement-weighting is L3 (ner.py /
# gazetteer.py). See gazetteer.py for the L1 matching engine and
# frequency-tier confidence design.
# ---------------------------------------------------------------------------
_person_name_type = _add(GazetteerRecognizer("PERSON_NAME", gazetteer.match_person_names))

# maskflow-pack-intl (if installed alongside) already registers PERSON_NAME
# context keywords for its spaCy NER recognizer. registry.register_*()'s
# context_keywords kwarg OVERWRITES CONTEXT_KEYWORDS[pii_type] rather than
# merging it, so passing one here directly would silently drop whichever
# pack's keywords were registered first (or vice versa, depending on import
# order) -- union explicitly instead. Standalone (pack-intl not installed),
# this is just pack-india's own set.
CONTEXT_KEYWORDS[_person_name_type] = tuple(
    dict.fromkeys(
        (
            *CONTEXT_KEYWORDS.get(_person_name_type, ()),
            # No bare "name"/"mr"/"ms"/"dr" here -- apply_context_boost()
            # matches keywords as plain substrings, and those four are
            # short enough to false-positive inside ordinary words
            # ("named", "summer", "items", "address") rather than only
            # matching the honorific/label they're meant to signal.
            "name is",
            "name:",
            "customer name",
            "applicant name",
            "contact person",
            "naam",
            "नाम",
            "श्री",
            "श्रीमती",
        )
    )
)

# ---------------------------------------------------------------------------
# INDIAN_ADDRESS -- L1 Gazetteer. Unit-marker/landmark-relative/
# locality-word structural rules and PIN_CODE reinforcement (L2) are
# registered further down. Deliberately low base confidence here (see
# gazetteer.match_indian_places) -- a bare state/city mention isn't an
# address on its own.
# ---------------------------------------------------------------------------
_add(
    GazetteerRecognizer(
        "INDIAN_ADDRESS",
        gazetteer.match_indian_places,
        context_keywords=(
            "address",
            "residing at",
            "located at",
            "resident of",
            # No bare "pin" -- substring-matches inside "spinning", "opinion",
            # etc. under apply_context_boost()'s plain-substring keyword check.
            "pincode",
            "pin code",
            "district",
            "pata",
            "पता",
            "निवास",
        ),
    )
)

# ---------------------------------------------------------------------------
# PERSON_NAME (Indian) -- L2 Structural. No context_keywords passed here --
# all but one of these patterns are high-confidence enough to clear
# threshold on structure alone (see patterns.py); passing context_keywords
# again would OVERWRITE (not merge into) the union already set up above.
# ---------------------------------------------------------------------------
_add(PatternRecognizer("PERSON_NAME", patterns.PERSON_NAME_HONORIFIC_RE, 0.85))
_add(PatternRecognizer("PERSON_NAME", patterns.PERSON_NAME_RELATIONAL_SUBJECT_RE, 0.8))
_add(PatternRecognizer("PERSON_NAME", patterns.PERSON_NAME_RELATIONAL_OBJECT_RE, 0.8))
_add(PatternRecognizer("PERSON_NAME", patterns.PERSON_NAME_INITIALS_PREFIX_RE, 0.8))
# Undotted trailing-initial form ("Srinivasan K") is structurally weaker
# (a lone trailing capital letter alone is common noise -- section labels,
# sentence-initial acronyms) -- context-gated like AADHAAR_MASKED/PIN_CODE.
_add(PatternRecognizer("PERSON_NAME", patterns.PERSON_NAME_INITIALS_SUFFIX_RE, 0.4))
_add(PatternRecognizer("PERSON_NAME", patterns.PERSON_NAME_FORM_FIELD_RE, 0.85))

# ---------------------------------------------------------------------------
# INDIAN_ADDRESS -- L2 Structural. Same no-context_keywords reasoning as
# above (would overwrite the L1 union).
# ---------------------------------------------------------------------------
_add(PatternRecognizer("INDIAN_ADDRESS", patterns.INDIAN_ADDRESS_UNIT_MARKER_RE, 0.85))
_add(PatternRecognizer("INDIAN_ADDRESS", patterns.INDIAN_ADDRESS_LANDMARK_RE, 0.6))
_add(PatternRecognizer("INDIAN_ADDRESS", patterns.INDIAN_ADDRESS_LOCALITY_RE, 0.8))

# ---------------------------------------------------------------------------
# L3 -- "NLP as recall only": spaCy entities down-weighted standalone,
# up-weighted on agreement with L1 (gazetteer) / L2 (structural) candidates
# of the same type (maskflow_core.registry.NerMapping.agreement_boost, see
# ner.py's detect_ner()). Needs maskflow-core[nlp] (spaCy) -- this pack now
# depends on it unconditionally, no longer spaCy-free.
#
# PERSON_NAME (Indian) via PERSON only -- CLAUDE.md's work order specifies
# L3 explicitly for PERSON_NAME; INDIAN_ADDRESS's own paragraph lists L1/L2
# features (gazetteers, unit markers, landmark phrases, locality words, PIN
# reinforcement) with no NLP layer mentioned. A GPE/LOC registration was
# tried and DELIBERATELY DROPPED this session: unlike PERSON_NAME (where
# two independent methods agreeing it's a name-shaped span really is
# stronger evidence), spaCy tagging a place GPE/LOC and gazetteer.py's
# INDIAN_PLACE_NAMES agreeing it's a place doesn't resolve INDIAN_ADDRESS's
# actual ambiguity -- "is this bare mention part of someone's address" vs.
# "a place mentioned in passing conversation" -- both methods just detect
# "this is a place name", which the gazetteer's 0.3 base already captures
# on its own. Wiring it up caused a measured regression (bare mentions like
# "Mumbai is a city in India." got promoted past threshold with no address
# context at all -- see the L3 report / india_l3_samples.py). INDIAN_ADDRESS
# recall beyond L1+L2 is intentionally left to a future landmark/context
# gazetteer, not spaCy's generic GPE/LOC tagging.
#
# maskflow-pack-intl ALSO registers the "PERSON" spaCy label
# (register_ner_recognizer's NER_RECOGNIZERS dict holds one mapping per
# label, so whichever pack imports last -- pack-india, in the
# maskflow-sdk/maskflow-cli bundled configuration -- wins). Deliberately
# NOT down-weighted from pack-intl's existing 0.75 standalone baseline:
# doing so would silently regress bare-NER PERSON_NAME recall for every
# NON-Indian name too (pack-intl's own PERSON_NAME_SAMPLES fixtures rely on
# spaCy firing alone, with no honorific/context phrase, e.g. "John Smith
# called yesterday afternoon.") -- a real, tested, shipped behavior this
# session chose not to break for a "down-weight standalone" reading that
# the work order scoped to this pack's OWN L3 layer, not to pack-intl's.
# agreement_boost=0.2 still gives genuine upside (0.75 -> 0.95) whenever
# L1/L2 independently confirms the same span. Preserving 0.75 standalone
# does mean this pack inherits pack-intl's existing false-positive class on
# common-word/name collisions ("Rose", "Lily", "Devi" as PERSON_NAME with
# no context) -- confirmed PRE-EXISTING in pack-intl alone, not introduced
# this session; see the L3 report.
_add(NlpRecognizer("PERSON", "PERSON_NAME", 0.75, agreement_boost=0.2))


# ---------------------------------------------------------------------------
# Strategy.SURROGATE fake-value generators -- see surrogates.py's module
# docstring for what "synthetic" means here (random-within-valid-shape, not
# drawn from any real-world registry). Registered for every type this pack
# owns; Strategy.SURROGATE falls back to Strategy.REPLACE for anything not
# listed here (see masking.py's surrogate_substitute()), so this list is the
# single source of truth for "which India types actually get a surrogate."
# ---------------------------------------------------------------------------
register_surrogate_generator(
    "AADHAAR",
    surrogates.surrogate_aadhaar,
    "random digits satisfying the Verhoeff checksum, 12 (UID) or 16 (VID) "
    "digits matching the original's length -- not drawn from any real "
    "UIDAI-issued range",
)
register_surrogate_generator(
    "AADHAAR_MASKED",
    surrogates.surrogate_aadhaar_masked,
    "same masked display shape (8 masked digits + 4 real-looking digits) "
    "with a freshly random last-4 group",
)
register_surrogate_generator(
    "PAN",
    surrogates.surrogate_pan,
    "random 5 letters + 4 digits + 1 letter, 4th letter restricted to PAN's "
    "published holder-category set -- no checksum exists to satisfy",
)
register_surrogate_generator(
    "GSTIN",
    surrogates.surrogate_gstin,
    "random state code (01-38) + surrogate PAN + entity number + 'Z' + a "
    "correctly computed mod-36 checksum character",
)
register_surrogate_generator(
    "IFSC",
    surrogates.surrogate_ifsc,
    "a real, published RBI bank code (data/ifsc_bank_codes.py) + random "
    "6-char branch code -- the bank code lookup is IFSC's only structural "
    "check, same as the pack's own validator",
)
register_surrogate_generator(
    "UPI_VPA",
    surrogates.surrogate_upi_vpa,
    "random handle + a real, published NPCI PSP handle (data/upi_handles.py)",
)
register_surrogate_generator(
    "INDIAN_MOBILE",
    surrogates.surrogate_indian_mobile,
    "random 10-digit number starting 6-9 (TRAI's assignable range), "
    "preserving the original's +91/0/bare prefix style",
)
register_surrogate_generator(
    "PIN_CODE",
    surrogates.surrogate_pin_code,
    "random 6-digit code, first digit 1-8 (India Post's assignable zones)",
)
register_surrogate_generator(
    "VOTER_ID",
    surrogates.surrogate_voter_id,
    "random 3 letters + 7 digits (EPIC number shape, no published checksum)",
)
register_surrogate_generator(
    "INDIAN_PASSPORT",
    surrogates.surrogate_indian_passport,
    "random 8-char inline number, or a full TD3 MRZ block with all four "
    "ICAO 9303 check digits correctly computed, matching whichever form "
    "the original was",
)
register_surrogate_generator(
    "DRIVING_LICENCE",
    surrogates.surrogate_driving_licence,
    "a real, published state RTO code (data/indian_state_rto_codes.py) + "
    "random office/year/serial digits",
)
register_surrogate_generator(
    "VEHICLE_REG",
    surrogates.surrogate_vehicle_reg,
    "a real, published state RTO code + random office/series/number",
)
register_surrogate_generator(
    "ABHA_NUMBER",
    surrogates.surrogate_abha_number,
    "random 14 digits in 2-4-4-4 groups -- no published NDHM checksum to "
    "satisfy",
)
register_surrogate_generator(
    "ABHA_ADDRESS",
    surrogates.surrogate_abha_address,
    "random handle @ abdm/sbx, ABDM's own domain suffixes",
)
register_surrogate_generator(
    "BANK_ACCOUNT_IN",
    surrogates.surrogate_bank_account,
    "random digits in the original's own length (9-18 digits) -- no "
    "cross-bank checksum exists",
)
register_surrogate_generator(
    "PERSON_NAME",
    surrogates.surrogate_person_name,
    "a name drawn from this pack's own bundled Indian-name gazetteer "
    "(data/indian_names.py), matching the original's word count",
)
register_surrogate_generator(
    "INDIAN_ADDRESS",
    surrogates.surrogate_indian_address,
    "a fabricated address built from this pack's own bundled city/state "
    "lists (data/indian_places.py) and locality-suffix vocabulary -- never "
    "a real street address",
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
