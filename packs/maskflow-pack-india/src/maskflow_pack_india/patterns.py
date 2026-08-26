"""Regex patterns and structural/checksum validators for India-specific PII
types. Each validator(value) -> float | None returns an adjusted confidence,
or None to reject the match entirely -- see checksums.py for the Verhoeff
(AADHAAR) and GSTIN check-digit algorithms these call into. __init__.py
registers these against maskflow-core via register_pattern().
"""

from __future__ import annotations

import re

from .checksums import gstin_is_valid, verhoeff_is_valid
from .data.ifsc_bank_codes import IFSC_BANK_CODES
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
