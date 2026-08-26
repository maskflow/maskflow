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
a real person's or business's identifier -- CLAUDE.md rule 2. Likewise every
INDIAN_PASSPORT MRZ block is GENERATED (via mrz_line1_generate /
mrz_line2_generate). PAN/IFSC/UPI/mobile/PIN/voter-ID/passport-number/DL/
vehicle-reg/ABHA/bank-account values are hand-picked synthetic strings
satisfying each type's structural rules (state/RTO codes drawn from the
bundled data sets); several of these types have no public checksum to
generate against (CLAUDE.md explicitly forbids inventing one).
"""

from dataclasses import dataclass

import maskflow_pack_india  # noqa: F401 -- import side effect registers PIIType.AADHAAR etc.
from maskflow_core.entities import PIIType
from maskflow_pack_india.checksums import mrz_line1_generate, mrz_line2_generate


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

# Prefixed (+91/0) INDIAN_MOBILE numbers -- get full confidence without
# context, per validate_indian_mobile().
INDIAN_MOBILE_PREFIXED_SAMPLES = [
    Sample(
        "Reach the delivery agent at +919876543210 for updates.",
        [(PIIType.INDIAN_MOBILE, "+919876543210")],
    ),
    Sample(
        "Alternate contact: 09123456789.",
        [(PIIType.INDIAN_MOBILE, "09123456789")],
    ),
]

# Bare (no prefix) mobile number -- needs a nearby context keyword to clear
# DEFAULT_MIN_CONFIDENCE (validate_indian_mobile() alone returns 0.35).
INDIAN_MOBILE_BARE_SAMPLES = [
    Sample(
        "My mobile number is 9876543211, call anytime.",
        [(PIIType.INDIAN_MOBILE, "9876543211")],
    ),
]

# PIN_CODE is always context-required -- every positive sample here pairs
# the 6-digit code with a state name or "pin/pincode" keyword.
PIN_CODE_SAMPLES = [
    Sample(
        "Ship the package to Bengaluru, Karnataka - 560001.",
        [(PIIType.PIN_CODE, "560001")],
    ),
    Sample(
        "Pincode: 110001 for the New Delhi office.",
        [(PIIType.PIN_CODE, "110001")],
    ),
]

VOTER_IDS_VALID = ["ABC1234567", "XYZ7654321"]

# 8-char inline passport number -- letter restricted to [A-PR-WY] (no
# Q/X/Z), no public checksum.
INDIAN_PASSPORTS_VALID = ["A1234567", "M9876543"]

# TD3 MRZ blocks -- GENERATED via mrz_line1_generate/mrz_line2_generate
# (checksum-valid, synthetic names/dates), not real passport data.
INDIAN_PASSPORT_MRZ_SAMPLES = [
    Sample(
        "Passport scan extracted:\n"
        + mrz_line1_generate("SHARMA", "ROHIT")
        + "\n"
        + mrz_line2_generate("A1234567", "900101", "300101", "PN1234567"),
        [
            (
                PIIType.INDIAN_PASSPORT,
                mrz_line1_generate("SHARMA", "ROHIT")
                + "\n"
                + mrz_line2_generate("A1234567", "900101", "300101", "PN1234567"),
            )
        ],
    ),
]

# state(2) + RTO(2) + issue year(4) + serial(7), state code drawn from
# data/indian_state_rto_codes.py.
DRIVING_LICENCES_VALID = ["MH1420110012345", "KA05 2015 0098765"]

# state(2) + RTO(1-2) + series(1-2 letters) + number(4).
VEHICLE_REGS_VALID = ["MH12AB1234", "KA05MJ1234", "TN09CD5678"]

# 14 digits, 2-4-4-4 grouping -- always context-required (no checksum). Last
# digit of the unspaced value deliberately isn't Luhn-valid -- maskflow-sdk
# loads pack-intl's CREDIT_CARD (any 13-19 digit run, Luhn-validated)
# alongside this pack, and a validated CREDIT_CARD span would win overlap
# resolution over an unvalidated ABHA_NUMBER span on the same text.
ABHA_NUMBERS_VALID = ["12-3456-7890-1234", "34567890123450"]

ABHA_ADDRESSES_VALID = ["priya.sharma@abdm", "rahul.kumar@sbx"]

# 9-18 digits, first digit deliberately outside AADHAAR's [2-9] first-digit
# range so these don't ambiguously double as AADHAAR-shaped candidates in
# the fixture itself -- always context-required (no checksum).
BANK_ACCOUNTS_IN_VALID = ["011234567890123", "098765432109"]

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
    # INDIAN_MOBILE-shaped but first digit outside [6-9].
    "Contact 5876543210 was logged for the wrong department.",
    # PIN_CODE-shaped (6 digits, "postal code" context present) but first
    # digit is 9 -- India Post's zone 9 (army post offices) is excluded.
    "Postal code 912345 for the location.",
    # VOTER_ID-shaped context present but only 2 letters, not 3.
    "Voter ID AB1234567 registered.",
    # INDIAN_PASSPORT-shaped but first letter 'Q' is outside the issuing
    # letter set (MEA never issues Q/X/Z as the first character).
    "Passport number Q1234567 issued.",
    # DRIVING_LICENCE-shaped but 'ZZ' isn't a real state RTO code.
    "Driving licence ZZ1420110012345 valid till 2030.",
    # VEHICLE_REG-shaped but 'ZZ' isn't a real state RTO code.
    "Vehicle number ZZ12AB1234 parked outside.",
    # ABHA_NUMBER-shaped context present but only 13 digits, not 14.
    "ABHA number 1234567890123 was verified for the health record.",
    # ABHA_ADDRESS-shaped ("health id" context present) but the domain is
    # neither abdm nor sbx (and isn't a known UPI PSP handle either).
    "Health ID rahul.k@randomclinic was rejected as invalid.",
    # BANK_ACCOUNT_IN-shaped context present but only 8 digits (below the
    # 9-18 digit range).
    "Account number 12345678 was created.",
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
    + INDIAN_MOBILE_PREFIXED_SAMPLES
    + INDIAN_MOBILE_BARE_SAMPLES
    + PIN_CODE_SAMPLES
    + _samples(PIIType.VOTER_ID, "Voter ID card number {value} on file.", VOTER_IDS_VALID)
    + _samples(PIIType.INDIAN_PASSPORT, "Passport number: {value}.", INDIAN_PASSPORTS_VALID)
    + INDIAN_PASSPORT_MRZ_SAMPLES
    + _samples(
        PIIType.DRIVING_LICENCE,
        "Driving licence number {value} valid till 2030.",
        DRIVING_LICENCES_VALID,
    )
    + _samples(
        PIIType.VEHICLE_REG, "Vehicle registration number {value} on file.", VEHICLE_REGS_VALID
    )
    + _samples(
        PIIType.ABHA_NUMBER, "ABHA number {value} linked to health records.", ABHA_NUMBERS_VALID
    )
    + _samples(PIIType.ABHA_ADDRESS, "ABHA address {value} used for linking.", ABHA_ADDRESSES_VALID)
    + _samples(
        PIIType.BANK_ACCOUNT_IN,
        "Bank account number {value} for salary credit.",
        BANK_ACCOUNTS_IN_VALID,
    )
    + MULTI_ENTITY_SAMPLES
)
