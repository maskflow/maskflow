"""Canonical taxonomy (the corpus's own positive labels) and each adapter's
raw-label -> canonical-label map.

Taxonomy comes from `canonical_labels(docs)` (reused from
bench.indiapii.harness) -- never a hardcoded list. Maps are intentionally
partial: an unmapped raw label is dropped before scoring, not counted as a
false positive against an unrelated type.
"""

from __future__ import annotations

from bench.indiapii.harness.labels import canonical_labels, identity_map

__all__ = [
    "LABEL_DESCRIPTIONS",
    "NAIVE_REGEX_LABEL_MAP",
    "PRESIDIO_LABEL_MAP",
    "canonical_labels",
    "identity_map",
]

LABEL_DESCRIPTIONS: dict[str, str] = {
    "AADHAAR": "12-digit Aadhaar, may be spaced in groups of 4",
    "PAN": "10-char PAN (5 letters + 4 digits + 1 letter)",
    "GSTIN": "15-char GST identification number",
    "IFSC": "11-char bank branch code",
    "UPI_VPA": "UPI address, username@bank-handle",
    "INDIAN_MOBILE": "10-digit Indian mobile, optional +91",
    "CREDIT_CARD": "13-19 digit Luhn-valid card number",
    "EMAIL": "an email address",
    "IP_ADDRESS": "an IPv4 or IPv6 address",
    "API_KEY": "an API key / secret token (sk-..., ghp_..., AIza...)",
    "AWS_KEY": "an AWS access key id (AKIA/ASIA + 16)",
    "JWT": "a JSON Web Token (eyJ....eyJ....sig)",
    "PERSON_NAME": "a person's name",
}

# Presidio predefined recognizers. No Aadhaar/PAN/GSTIN/IFSC/UPI/AWS/JWT
# equivalent -> 0 recall on those is expected, not a bug.
PRESIDIO_LABEL_MAP: dict[str, str] = {
    "EMAIL_ADDRESS": "EMAIL",
    "IP_ADDRESS": "IP_ADDRESS",
    "CREDIT_CARD": "CREDIT_CARD",
    "PHONE_NUMBER": "INDIAN_MOBILE",
    "PERSON": "PERSON_NAME",
}

NAIVE_REGEX_LABEL_MAP: dict[str, str] = {
    "EMAIL_SHAPED": "EMAIL",
    "IPV4_SHAPED": "IP_ADDRESS",
    "CARD_SHAPED": "CREDIT_CARD",
    "PHONE_SHAPED": "INDIAN_MOBILE",
    "AADHAAR_SHAPED": "AADHAAR",
    "PAN_SHAPED": "PAN",
    "AWS_KEY_SHAPED": "AWS_KEY",
    "JWT_SHAPED": "JWT",
}
