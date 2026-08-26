"""Labeled PII examples used to measure detection accuracy, mirroring
maskflow-pack-intl's fixtures/pii_samples.py structure.

POSITIVE_SAMPLES: each sample's `expected` findings must all be present in
detect()'s output (a recall check -- extra correct detections elsewhere in
the same sentence are fine).

NEGATIVE_SAMPLES: plain sentences, format-variant misses (e.g. an AADHAAR-
shaped number starting 0/1), and structurally-shaped-but-checksum-invalid
values that must produce *zero* findings -- a precision check.

Every AADHAAR/AADHAAR_VID/GSTIN value below is GENERATED (via
maskflow_pack_india.checksums.verhoeff_generate / gstin_checksum_char), not
a real person's or business's identifier -- CLAUDE.md rule 2. PAN/IFSC/UPI
values are hand-picked synthetic strings satisfying each type's structural
rules; PAN has no checksum to generate against (CLAUDE.md explicitly
forbids inventing one).
"""

from dataclasses import dataclass

import maskflow_pack_india  # noqa: F401 -- import side effect registers PIIType.AADHAAR etc.
from maskflow_core.entities import PIIType


@dataclass
class Sample:
    text: str
    expected: list[tuple[PIIType, str]]


def _samples(pii_type: PIIType, template: str, values: list[str]) -> list[Sample]:
    return [Sample(template.format(value=v), [(pii_type, v)]) for v in values]


# Verhoeff-valid, GENERATED synthetic AADHAAR UIDs (12 digits, unspaced).
AADHAAR_UNSPACED = [
    "234567890124",
    "345678901238",
    "456789012341",
    "789012345674",
    "912345678905",
]

# Same generated digits, spaced/hyphenated -- exercises the separator-
# consistency backreference in AADHAAR_RE.
AADHAAR_SPACED = ["2345 6789 0124", "3456 7890 1238", "4567 8901 2341"]
AADHAAR_HYPHENATED = ["7890-1234-5674", "9123-4567-8905"]

# Verhoeff-valid, GENERATED synthetic 16-digit VIDs.
AADHAAR_VID = ["2345678901234565", "9123456789012346"]

# Masked display form -- last 4 digits real, first 8 replaced. Needs nearby
# context to clear the 0.5 default threshold (see __init__.py's 0.45 base).
AADHAAR_MASKED_SAMPLES = [
    Sample(
        "Your masked Aadhaar on file: XXXX XXXX 9012.",
        [(PIIType.AADHAAR_MASKED, "XXXX XXXX 9012")],
    ),
    Sample(
        "Aadhaar ending in the usual format xxxxxxxx5678 was verified.",
        [(PIIType.AADHAAR_MASKED, "xxxxxxxx5678")],
    ),
    Sample(
        "आधार: XXXX-XXXX-4321 पर सत्यापन हुआ।",
        [(PIIType.AADHAAR_MASKED, "XXXX-XXXX-4321")],
    ),
]

# Structurally valid PANs (4th char in the holder-category set P/C/H/F/A);
# no checksum exists for the final letter (CLAUDE.md: do not invent one).
PANS_VALID = ["ABCPE1234F", "AAACX9876K", "XYZHP4321Q", "MNOFA7654B", "PQRAT2345C"]

# GSTIN = state(2) + PANS_VALID[i] + entity + 'Z' + GENERATED checksum char.
GSTINS_VALID = [
    "27ABCPE1234F1ZB",
    "07AAACX9876K2ZH",
    "33XYZHP4321Q1ZE",
    "29MNOFA7654B1Z7",
    "19PQRAT2345C3ZX",
]

# Bank codes drawn from data/ifsc_bank_codes.py; branch suffix is arbitrary
# alnum (IFSC has no per-branch checksum, only the bank-code lookup).
IFSCS_VALID = [
    "HDFC0001234",
    "SBIN0000123",
    "ICIC0000456",
    "UTIB0002345",
    "PYTM0123456",
]

# Handles drawn from data/upi_handles.py.
UPI_VPAS_VALID = [
    "priya.sharma@okhdfcbank",
    "raj_kumar@ybl",
    "anita.rao@paytm",
    "vikram@oksbi",
    "deepa.iyer@okaxis",
]

MULTI_ENTITY_SAMPLES = [
    Sample(
        "KYC details: PAN ABCPE1234F, Aadhaar 234567890124, UPI vikram@oksbi for verification.",
        [
            (PIIType.PAN, "ABCPE1234F"),
            (PIIType.AADHAAR, "234567890124"),
            (PIIType.UPI_VPA, "vikram@oksbi"),
        ],
    ),
    Sample(
        "GSTIN 27ABCPE1234F1ZB registered; bank transfer via IFSC HDFC0001234.",
        [
            (PIIType.GSTIN, "27ABCPE1234F1ZB"),
            (PIIType.IFSC, "HDFC0001234"),
        ],
    ),
    Sample(
        "मेरा आधार नंबर 345678901238 है और पैन कार्ड AAACX9876K है।",
        [
            (PIIType.AADHAAR, "345678901238"),
            (PIIType.PAN, "AAACX9876K"),
        ],
    ),
]

NEGATIVE_SAMPLES = [
    "Order number 234567890124567 was shipped today.",
    # AADHAAR-length but starts with 0/1 -- UIDAI never issues this, so the
    # regex's [2-9] first-digit class excludes it entirely.
    "Reference 123456789012 does not match our records.",
    "Reference 023456789012 does not match our records.",
    # AADHAAR-shaped (starts 2-9, 12 digits) but Verhoeff-invalid.
    "Applicant number 234567890125 was rejected during validation.",
    # PAN-shaped but 4th char outside the holder-category set.
    "Reference code ABCDE1234F was logged for audit.",
    # GSTIN-shaped but checksum character corrupted. Embedded PAN portion
    # also uses an invalid holder-category char ('D') so this is a true
    # zero-finding negative -- see test_gstin.py for the case where a bad
    # GSTIN checksum still legitimately leaves a *valid* embedded PAN behind
    # (that's a correct PAN detection, not a false positive, so it isn't
    # exercised as a whole-string-empty negative here).
    "Filing reference 27ABCDE1234F1ZA could not be matched.",
    # GSTIN-shaped but state code out of the 01-38 range (same invalid
    # embedded-PAN category char, for the same reason as above).
    "Filing reference 99ABCDE1234F1ZP could not be matched.",
    # IFSC-shaped but bank code isn't in the bundled RBI list.
    "Transfer code ZZZZ0123456 was not recognized by the gateway.",
    # UPI-handle-shaped but the PSP after '@' isn't a known NPCI handle.
    "Contact handle raviteja@randomhandle isn't a real payment address.",
    "Please review the quarterly report before Friday.",
    "The stock price rose by 4.5 percent today.",
    "Our server uptime this month was 99.98 percent.",
]

POSITIVE_SAMPLES: list[Sample] = (
    _samples(PIIType.AADHAAR, "My Aadhaar number is {value}, please verify.", AADHAAR_UNSPACED)
    + _samples(PIIType.AADHAAR, "आधार संख्या {value} दर्ज करें।", AADHAAR_SPACED)
    + _samples(PIIType.AADHAAR, "Aadhar no. {value} was submitted for KYC.", AADHAAR_HYPHENATED)
    + _samples(PIIType.AADHAAR, "UIDAI VID on file: {value}.", AADHAAR_VID)
    + AADHAAR_MASKED_SAMPLES
    + _samples(PIIType.PAN, "PAN card number: {value}.", PANS_VALID)
    + _samples(PIIType.GSTIN, "GSTIN registered for this business: {value}.", GSTINS_VALID)
    + _samples(PIIType.IFSC, "Please use IFSC code {value} for the transfer.", IFSCS_VALID)
    + _samples(PIIType.UPI_VPA, "Pay to UPI ID {value} for the order.", UPI_VPAS_VALID)
    + MULTI_ENTITY_SAMPLES
)
