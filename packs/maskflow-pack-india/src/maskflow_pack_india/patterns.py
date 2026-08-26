"""Regex patterns and structural/checksum validators for India-specific PII
types. Each validator(value) -> float | None returns an adjusted confidence,
or None to reject the match entirely -- see checksums.py for the Verhoeff
(AADHAAR), GSTIN, and MRZ (INDIAN_PASSPORT) check-digit algorithms these
call into. __init__.py registers these against maskflow-core via
register_pattern().
"""

from __future__ import annotations

import re

from .checksums import gstin_is_valid, indian_passport_mrz_line2_is_valid, verhoeff_is_valid
from .data.ifsc_bank_codes import IFSC_BANK_CODES
from .data.indian_state_rto_codes import INDIAN_STATE_RTO_CODES
from .data.upi_handles import UPI_PSP_HANDLES

# ---------------------------------------------------------------------------
# AADHAAR -- 12-digit UID, 16-digit VID, and masked display forms.
# ---------------------------------------------------------------------------

# 12 digits, never starting 0/1 (UIDAI never issues those as a first digit).
# group(1) is the whole matched run including separators -- detection.py's
# _scan_pattern uses group(1) as the span whenever the regex has ANY group,
# so the outer group must span the full value, not just a sub-piece of it.
# group(2) is the separator, backreferenced via \2 so both gaps must match
# (both spaced, both hyphenated, or both absent -- never mixed).
AADHAAR_RE = re.compile(r"(?<!\d)([2-9]\d{3}([ -]?)\d{4}\2\d{4})(?!\d)")

# 16-digit Virtual ID (VID) -- same first-digit rule and Verhoeff checksum,
# one more group of 4 digits than the UID form.
AADHAAR_VID_RE = re.compile(r"(?<!\d)([2-9]\d{3}([ -]?)\d{4}\2\d{4}\2\d{4})(?!\d)")

# Masked display form banks/agencies show back to a user, e.g. "XXXX XXXX
# 9012" or "xxxxxxxx9012" -- first 8 digits replaced with a mask character
# (X or *), last 4 digits real. Unverifiable (8 of 12 digits are gone), so
# this is registered as its own lower-confidence, unvalidated entity type
# rather than fed through validate_aadhaar().
AADHAAR_MASKED_RE = re.compile(r"(?<!\w)([xX*]{4}([ -]?)[xX*]{4}\2\d{4})(?!\w)")


def validate_aadhaar(value: str) -> float | None:
    digits = re.sub(r"[ -]", "", value)
    if len(digits) not in (12, 16) or not digits.isdigit():
        return None
    # 0.9 base leaves room for the context boost (CONTEXT_KEYWORDS in
    # __init__.py) to reach MAX_CONFIDENCE without a checksum-valid AADHAAR
    # ever scoring below a checksum-valid but context-free match on some
    # other overlapping type.
    return 0.9 if verhoeff_is_valid(digits) else None


# ---------------------------------------------------------------------------
# PAN -- 5 letters + 4 digits + 1 letter, 4th letter constrained to a known
# holder-category set. No public checksum exists for the final letter.
# ---------------------------------------------------------------------------

_PAN_FOURTH_CHAR_CATEGORIES = "PCHFATBLJG"

# Standalone PAN: boundaries exclude alnum neighbors on both sides, so a PAN
# embedded directly inside a longer alnum run (e.g. a GSTIN) does NOT match
# here -- see PAN_EMBEDDED_IN_GSTIN_RE below for that case specifically.
PAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])")

# The PAN embedded in a GSTIN's characters 3-12: preceded by the 2-digit
# state code, followed by <entity_number><'Z'><checksum>. A valid GSTIN's
# embedded PAN also surfaces as its own PAN candidate span this way;
# spanset.py's CONTAINS resolution (CLAUDE.md design decision #1) then picks
# the longer, equally-validated GSTIN span over the shorter contained PAN.
PAN_EMBEDDED_IN_GSTIN_RE = re.compile(r"(?<=\d{2})[A-Z]{5}[0-9]{4}[A-Z](?=[0-9A-Z]Z[0-9A-Z])")


def validate_pan(value: str) -> float | None:
    if len(value) != 10:
        return None
    if value[3] not in _PAN_FOURTH_CHAR_CATEGORIES:
        return None
    # 0.85, not higher: this is a structural check (holder-category letter
    # only), not a checksum -- PAN's final letter has no public checksum, so
    # this can never be as confident as a Verhoeff- or mod-97-validated span.
    return 0.85


# ---------------------------------------------------------------------------
# GSTIN -- 15 chars: state code (01-38) + PAN + entity number + 'Z' + base-36
# checksum. Reuses validate_pan() for the embedded PAN's structural check.
# ---------------------------------------------------------------------------

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")

_MIN_STATE_CODE = 1
_MAX_STATE_CODE = 38


def validate_gstin(value: str) -> float | None:
    if len(value) != 15:
        return None
    if not (_MIN_STATE_CODE <= int(value[:2]) <= _MAX_STATE_CODE):
        return None
    if validate_pan(value[2:12]) is None:
        return None
    if value[13] != "Z":
        return None
    return 0.95 if gstin_is_valid(value) else None


# ---------------------------------------------------------------------------
# IFSC -- 4-letter bank code + literal '0' + 6 alnum branch code. Bank code
# validated against a bundled, periodically-refreshed RBI code list (see
# data/ifsc_bank_codes.py) -- there is no per-character checksum on an IFSC,
# the bank-code lookup IS the structural check.
# ---------------------------------------------------------------------------

IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")


def validate_ifsc(value: str) -> float | None:
    if len(value) != 11 or value[4] != "0":
        return None
    if value[:4] not in IFSC_BANK_CODES:
        return None
    return 0.9


# ---------------------------------------------------------------------------
# UPI_VPA -- handle@psp, PSP validated against a bundled NPCI handle list
# (see data/upi_handles.py). The trailing `(?!\.[A-Za-z])` keeps this from
# matching the first label of a real multi-label domain (name@gmail.com):
# the psp group is letters-only (no dot), so on "name@gmail.com" it can only
# ever match up to "gmail" -- the lookahead then vetoes that because a
# dot-then-letter follows, i.e. this is actually someone's email domain, not
# a UPI handle. A handle NOT in the bundled list is rejected here (returns
# None) rather than guessed at, so a general-purpose EMAIL recognizer (e.g.
# maskflow-pack-intl's) gets first claim on anything that looks like mail.
# ---------------------------------------------------------------------------

UPI_VPA_RE = re.compile(r"\b[A-Za-z0-9.\-_]{2,256}@[A-Za-z]{2,64}(?!\.[A-Za-z])\b")


def validate_upi_vpa(value: str) -> float | None:
    handle, _, psp = value.partition("@")
    if not handle or not psp:
        return None
    if psp.lower() not in UPI_PSP_HANDLES:
        return None
    return 0.95


# ---------------------------------------------------------------------------
# INDIAN_MOBILE -- 10 digits starting 6-9 (TRAI never assigns a mobile
# number starting 0-5), optionally preceded by a +91 country code or a 0
# trunk prefix. One regex + one confidence-branching validator rather than
# a two-pattern split (contrast AADHAAR/AADHAAR_VID): an explicit prefix is
# unambiguous on its own, a bare 10-digit run is not, so the validator
# returns a high confidence for the former and a below-threshold one for
# the latter -- CLAUDE.md's "require prefix OR a context keyword for full
# score" expressed as one rule.
# ---------------------------------------------------------------------------

INDIAN_MOBILE_RE = re.compile(r"(?<!\d)((?:\+91[-\s]?|0)?[6-9]\d{9})(?!\d)")


def validate_indian_mobile(value: str) -> float | None:
    has_prefix = value[0] in "+0"
    return 0.8 if has_prefix else 0.35


# ---------------------------------------------------------------------------
# PIN_CODE -- 6-digit postal code, first digit 1-8 (India Post's zone 9 is
# reserved for army post offices and has its own separate context). No
# checksum exists; a bare 6-digit number is extremely ambiguous (order
# numbers, reference codes, ...) so this is always context-required --
# base confidence starts well below DEFAULT_MIN_CONFIDENCE and needs a
# nearby pin/pincode/state-name/address keyword (see __init__.py) to clear
# the bar.
# ---------------------------------------------------------------------------

PIN_CODE_RE = re.compile(r"(?<!\d)([1-8]\d{5})(?!\d)")


# ---------------------------------------------------------------------------
# VOTER_ID (EPIC number) -- 3 letters + 7 digits. No public checksum is
# published for the letter/digit combination, so this is structural-only
# (same tier as PAN): the regex fully encodes the shape, so no validator
# function is needed -- base confidence alone (below) already reflects
# "shape-valid but unchecksummed."
# ---------------------------------------------------------------------------

VOTER_ID_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3}\d{7}(?![A-Za-z0-9])")


# ---------------------------------------------------------------------------
# INDIAN_PASSPORT -- inline 8-char number (1 letter, excluding Q/X/Z per
# the Ministry of External Affairs' issuing-letter set, + 7 digits) plus a
# full TD3 machine-readable-zone (MRZ) 2-line block, scoped to Indian
# passports by pinning the issuing-state/nationality field to "IND". The
# inline number has no public checksum; the MRZ block carries four
# independent ICAO 9303 check digits (see checksums.py), so it gets its
# own, much higher, validated confidence.
# ---------------------------------------------------------------------------

INDIAN_PASSPORT_RE = re.compile(r"(?<![A-Za-z0-9])[A-PR-WY][1-9]\d\s?\d{4}[1-9](?![A-Za-z0-9])")

# TD3 line 1: 'P' + document-type subcode + "IND" (issuing state) + a
# 39-char name field (letters and '<' filler only).
# TD3 line 2: 9-char document number + its check digit + "IND" (nationality)
# + 6-digit DOB + its check digit + sex (M/F/<) + 6-digit expiry + its check
# digit + 14-char personal-number field + its check digit + composite check
# digit. Every quantifier is a fixed count -- no unbounded/backtracking risk.
INDIAN_PASSPORT_MRZ_RE = re.compile(
    r"(P[A-Z<]IND[A-Z<]{39}\n[A-Z0-9<]{9}\dIND\d{6}\d[MF<]\d{6}\d[A-Z0-9<]{14}[A-Z0-9<]\d)",
    re.MULTILINE,
)


def validate_indian_passport_mrz(value: str) -> float | None:
    lines = value.split("\n")
    if len(lines) != 2:
        return None
    _line1, line2 = lines
    # 0.97: four independent ICAO check digits all agreeing is a stronger
    # signal than a single mod-97/Verhoeff checksum, so this sits above
    # every other validated confidence in this pack.
    return 0.97 if indian_passport_mrz_line2_is_valid(line2) else None


# ---------------------------------------------------------------------------
# DRIVING_LICENCE -- 2-letter state RTO code + 2-digit RTO office number +
# 4-digit issue year (19xx/20xx) + 7-digit serial, e.g. "MH12 20110012345".
# The RTO code lookup (data/indian_state_rto_codes.py) IS the structural
# check -- there is no per-character checksum on a DL number, same design
# as IFSC's bank-code lookup.
# ---------------------------------------------------------------------------

DRIVING_LICENCE_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Z]{2}\d{2}([- ]?)(?:19|20)\d{2}\2\d{7})(?![A-Za-z0-9])"
)


def validate_driving_licence(value: str) -> float | None:
    state_code = value[:2]
    if state_code not in INDIAN_STATE_RTO_CODES:
        return None
    return 0.85


# ---------------------------------------------------------------------------
# VEHICLE_REG -- 2-letter state RTO code + 1-2 digit RTO office number +
# 1-2 letter series + 4-digit number, e.g. "MH12AB1234". Same state-code-
# lookup-as-structural-check design as DRIVING_LICENCE, sharing the same
# bundled code set.
# ---------------------------------------------------------------------------

VEHICLE_REG_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Z]{2}[- ]?\d{1,2}[- ]?[A-Z]{1,2}[- ]?\d{4})(?![A-Za-z0-9])"
)


def validate_vehicle_reg(value: str) -> float | None:
    state_code = value[:2]
    if state_code not in INDIAN_STATE_RTO_CODES:
        return None
    return 0.85


# ---------------------------------------------------------------------------
# ABHA_NUMBER -- Ayushman Bharat Health Account, 14 digits in 2-4-4-4
# groups (e.g. "12-3456-7890-1234"). No checksum is registered here (NDHM's
# real check-digit scheme isn't part of this work order's scope) -- a bare
# 14-digit run is exactly as ambiguous as a bare AADHAAR-length run, so
# this is always context-required, mirroring AADHAAR_MASKED's design.
# ---------------------------------------------------------------------------

ABHA_NUMBER_RE = re.compile(r"(?<!\d)(\d{2}([- ]?)\d{4}\2\d{4}\2\d{4})(?!\d)")


# ---------------------------------------------------------------------------
# ABHA_ADDRESS -- handle@abdm or handle@sbx, the health-ID analogue of a UPI
# VPA. Same shape family and same "reject unless the suffix is on the known
# list" design as validate_upi_vpa -- "sbx" is ABDM's sandbox/test-domain
# suffix, still worth masking since sandbox addresses are still tied to a
# real health ID during testing/onboarding flows.
# ---------------------------------------------------------------------------

ABHA_ADDRESS_RE = re.compile(r"\b([A-Za-z0-9.\-_]{2,64}@[A-Za-z]{2,10})(?!\.[A-Za-z])\b")

_ABHA_ADDRESS_DOMAINS = frozenset({"abdm", "sbx"})


def validate_abha_address(value: str) -> float | None:
    handle, _, domain = value.partition("@")
    if not handle or domain.lower() not in _ABHA_ADDRESS_DOMAINS:
        return None
    return 0.9


# ---------------------------------------------------------------------------
# BANK_ACCOUNT_IN -- 9 to 18 digits (the range Indian banks actually issue
# account numbers in; no fixed length or checksum exists across banks). A
# bare digit run in this range is maximally ambiguous -- it overlaps
# AADHAAR (12 digits), AADHAAR_VID (16 digits), and INDIAN_MOBILE (10
# digits) in length alone -- so this is always context-required (account /
# a\/c / acct nearby). Where a checksum-validated type like AADHAAR also
# matches the same span, spanset resolution's "validated desc, score desc"
# ordering (CLAUDE.md design decision #1) makes the checksum-backed span
# win outright; BANK_ACCOUNT_IN only ever surfaces where nothing more
# specific also validated.
# ---------------------------------------------------------------------------

BANK_ACCOUNT_IN_RE = re.compile(r"(?<!\d)(\d{9,18})(?!\d)")

# ---------------------------------------------------------------------------
# PERSON_NAME (Indian) -- L2 Structural. Honorifics, relational markers,
# initials, and form-field labels are strong enough evidence to detect a
# name STRUCTURALLY even when it isn't in gazetteer.py's L1 word list --
# every pattern below feeds the same PIIType.PERSON_NAME L1 already
# registered (see __init__.py), so hits from both layers compete/merge in
# the same spanset.resolve() pass. All bounded (1-3 capitalised words max),
# no nested quantifiers -- CLAUDE.md rule 3.
# ---------------------------------------------------------------------------

# 1-3 capitalised words, e.g. "Sharma", "Priya Iyer", "Anjali Kumar Rao".
_NAME_RUN = r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2}"

# Honorific + capitalised name run, e.g. "Mr. Sharma", "Dr. Priya Iyer",
# "Shri Ramesh Chandra". Devanagari "श्री"/"श्रीमती" are already registered
# as PERSON_NAME context keywords (__init__.py) instead of matched here --
# they don't reliably precede a Latin-script capitalised run the way these
# English/transliterated honorifics do.
#
# KNOWN LIMITATION (documented, not fixed here -- L2 report,
# packs/maskflow-pack-india/tests/fixtures/india_l2_samples.py's
# PERSON_NAME_HARD_NEGATIVE_SAMPLES): "Dr. Reddy's" (the pharma brand)
# structurally matches identically to "Dr. Reddy" the person -- honorific +
# capitalised word is genuinely ambiguous without real-world entity
# knowledge. No cheap regex heuristic (e.g. penalizing a trailing "'s")
# fixes this without also losing recall on "Dr. Sharma's clinic" (a real,
# common, correct case), so this is left for L3's NLP disambiguation.
PERSON_NAME_HONORIFIC_RE = re.compile(
    rf"(?:Shri|Sri|Smt|Kum|Mr|Mrs|Ms|Dr|Prof|Late)\.?\s+({_NAME_RUN})"
)

# Relational marker: two separate patterns (not one two-group pattern)
# because detection.py's _scan_pattern only ever reads group(1) -- one
# captures the SUBJECT's name (before the marker), the other the relative's
# name (after), e.g. "Ramesh S/o Suresh Kumar" yields both "Ramesh" and
# "Suresh Kumar" as independent PERSON_NAME candidates.
PERSON_NAME_RELATIONAL_SUBJECT_RE = re.compile(
    rf"({_NAME_RUN})\s+(?:S/o|D/o|W/o|C/o|son of|daughter of|wife of)\b"
)
PERSON_NAME_RELATIONAL_OBJECT_RE = re.compile(
    rf"(?:S/o|D/o|W/o|C/o|son of|daughter of|wife of)\s+({_NAME_RUN})"
)

# Initials before a surname ("R. Venkataraman", "K.S. Rao") -- 1-3 single
# capital letters, each dot-terminated, then a capitalised word. The
# required dots make this structurally distinctive enough for a high
# standalone confidence (contrast the suffix-initial form below).
PERSON_NAME_INITIALS_PREFIX_RE = re.compile(r"((?:[A-Z]\.\s?){1,3}[A-Z][a-zA-Z]+)(?![a-zA-Z])")

# A given name followed by a single trailing initial, no dot ("Srinivasan
# K") -- inherently more ambiguous than the dotted prefix form (a lone
# trailing capital letter is weak evidence on its own, e.g. a mid-sentence
# acronym start), so this is context-gated rather than high-confidence
# standalone -- see __init__.py's PERSON_NAME context keywords.
PERSON_NAME_INITIALS_SUFFIX_RE = re.compile(r"([A-Z][a-zA-Z]{2,}\s+[A-Z])(?![a-zA-Z])")

# Form-field label immediately before a capitalised name run, e.g. "Name:
# Rohit Sharma", "Applicant Priya Iyer". "नाम" (Devanagari) is already a
# PERSON_NAME context keyword, same reasoning as the honorific pattern.
PERSON_NAME_FORM_FIELD_RE = re.compile(
    rf"(?:Name|Applicant|Customer Name)\s*[:\-]?\s+({_NAME_RUN})"
)

# ---------------------------------------------------------------------------
# INDIAN_ADDRESS -- L2 Structural. Unit markers, landmark-relative phrases,
# and locality-word suffixes are strong enough evidence to detect an
# address fragment structurally, on top of L1's gazetteer-only matching
# (gazetteer.match_indian_places). All bounded, no nested quantifiers.
# ---------------------------------------------------------------------------

# Unit marker + a following number (optionally letter-suffixed), e.g.
# "H.No. 123", "Flat 4B", "Sector 62", "Plot 45A", "Door No. 12".
INDIAN_ADDRESS_UNIT_MARKER_RE = re.compile(
    r"((?:H\.?\s?No\.?|Flat|Plot|Sector|Block|Phase|Door\s+No\.?)\s*[:\-]?\s*\d+[A-Za-z]?)"
)

# Landmark-relative phrase: preposition + a following proper-noun run, e.g.
# "near City Hospital", "opposite Ashoka Talkies".
#
# KNOWN LIMITATION (documented, not fixed here -- see the L2 report /
# india_l2_samples.py's INDIAN_ADDRESS_HARD_NEGATIVE_SAMPLES): capitalisation
# alone can't distinguish a genuine landmark from an ordinary noun someone
# happens to capitalise mid-sentence ("hiding behind Curtains") -- telling
# those apart needs a landmark gazetteer (out of scope) or real NLP (L3),
# not a regex. Left at this confidence because most real landmark-relative
# addresses DO look exactly like this, and lowering it further would cost
# more genuine recall than the false-positive rate here justifies.
INDIAN_ADDRESS_LANDMARK_RE = re.compile(rf"(?:near|opposite|behind|beside)\s+({_NAME_RUN})")

# Locality-word suffix, e.g. "Lajpat Nagar", "Green Park Colony", "Ashok
# Vihar" -- a capitalised word/run immediately before one of these suffixes
# is specific enough to be high-confidence on its own.
INDIAN_ADDRESS_LOCALITY_RE = re.compile(
    rf"({_NAME_RUN}\s+(?:Nagar|Colony|Vihar|Puram|Layout|Extension|Marg))"
)

# 6-digit PIN code, first digit 1-8 -- same shape as PIN_CODE_RE above, kept
# as its own local pattern (not reused directly) so gazetteer.py's PIN_CODE
# reinforcement can stay self-contained rather than importing detection
# internals just for a lookaround match.
INDIAN_PIN_CODE_SHAPE_RE = re.compile(r"(?<!\d)[1-8]\d{5}(?!\d)")
