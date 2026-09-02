"""entity_type -> (Severity, one-line plain-English "why this matters").

Severity is about *what an attacker or auditor can do with this class of
value if it left your control*, not about detector confidence. The
"why this matters" line is written for a decision-maker with no security
background -- it appears verbatim in the report's severity table.

Unknown / pack-added types fall back to MEDIUM with a generic line, so a
new recognizer never breaks the report; add an entry here (with a docs
note) when a pack ships a new type.
"""

from __future__ import annotations

from enum import IntEnum


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.title()


_TABLE: dict[str, tuple[Severity, str]] = {
    "AADHAAR": (
        Severity.CRITICAL,
        "A national identity number under the Aadhaar Act. Exposure enables "
        "identity theft and impersonation, and is a reportable personal-data "
        "breach under the DPDP Act.",
    ),
    "AADHAAR_MASKED": (
        Severity.LOW,
        "Only the last four Aadhaar digits. Low risk alone, but confirms the "
        "individual holds an Aadhaar and aids social-engineering.",
    ),
    "PAN": (
        Severity.CRITICAL,
        "The Permanent Account Number ties directly to a person's tax and "
        "financial identity and is accepted as KYC almost everywhere; leakage "
        "enables financial fraud.",
    ),
    "GSTIN": (
        Severity.MEDIUM,
        "A business tax registration. Semi-public, but embeds the entity's PAN "
        "and links the organisation to named individuals.",
    ),
    "BANK_ACCOUNT_IN": (
        Severity.CRITICAL,
        "A bank account number. Combined with an IFSC or a name it is enough to "
        "attempt unauthorised transfers or targeted fraud.",
    ),
    "IFSC": (
        Severity.LOW,
        "Identifies a bank branch. Public information on its own; raises risk "
        "only alongside an account number.",
    ),
    "UPI_VPA": (
        Severity.HIGH,
        "A UPI payment address. Directly usable to solicit or misdirect "
        "payments and to phish the account holder.",
    ),
    "CREDIT_CARD": (
        Severity.CRITICAL,
        "A payment card number. Exposure is a PCI-DSS reportable event and "
        "enables direct financial fraud.",
    ),
    "IBAN": (
        Severity.HIGH,
        "An international bank account identifier, sufficient for fraudulent "
        "direct-debit setup in many jurisdictions.",
    ),
    "INDIAN_PASSPORT": (
        Severity.CRITICAL,
        "A passport number is a strong government identifier used for travel and "
        "KYC; leakage enables impersonation and document fraud.",
    ),
    "VOTER_ID": (
        Severity.HIGH,
        "The EPIC number is a government identity document accepted as KYC and address proof.",
    ),
    "DRIVING_LICENCE": (
        Severity.HIGH,
        "A driving licence number is a widely accepted identity and address "
        "proof; exposure aids impersonation.",
    ),
    "VEHICLE_REG": (
        Severity.MEDIUM,
        "A vehicle registration links to the registered owner via the RTO "
        "database and can enable stalking or targeted contact.",
    ),
    "INDIAN_MOBILE": (
        Severity.MEDIUM,
        "A mobile number is a primary contact identifier and a common "
        "second-factor / OTP channel; exposure enables phishing and SIM-swap "
        "targeting.",
    ),
    "PHONE": (
        Severity.MEDIUM,
        "A phone number is a primary contact identifier and OTP channel; "
        "exposure enables phishing and account-recovery attacks.",
    ),
    "EMAIL": (
        Severity.MEDIUM,
        "An email address is a primary account identifier and recovery channel; "
        "exposure enables phishing and credential-stuffing targeting.",
    ),
    "PERSON_NAME": (
        Severity.MEDIUM,
        "A person's name. Low risk alone, but it is the link that turns every "
        "other exposed field into information about a specific, identifiable "
        "individual under the DPDP Act.",
    ),
    "INDIAN_ADDRESS": (
        Severity.HIGH,
        "A postal address reveals where an identifiable person lives or works, "
        "enabling physical targeting and stronger identity fraud.",
    ),
    "ADDRESS": (
        Severity.HIGH,
        "A postal address reveals where an identifiable person lives or works, "
        "enabling physical targeting and stronger identity fraud.",
    ),
    "PIN_CODE": (
        Severity.LOW,
        "A postal code narrows location to an area, not an individual; a weak signal on its own.",
    ),
    "DATE_OF_BIRTH": (
        Severity.HIGH,
        "Date of birth is a near-universal identity-verification field; combined "
        "with a name it defeats many KYC checks.",
    ),
    "IP_ADDRESS": (
        Severity.LOW,
        "An IP address is a coarse location and network identifier; personal "
        "data under the DPDP Act but low direct-harm risk.",
    ),
    "ABHA_NUMBER": (
        Severity.HIGH,
        "The ABHA health-account number links to a person's medical records "
        "under the Ayushman Bharat Digital Mission.",
    ),
    "ABHA_ADDRESS": (
        Severity.HIGH,
        "The ABHA address is a health-account identifier that can be used to "
        "request linkage to medical records.",
    ),
    "SSN": (
        Severity.CRITICAL,
        "A national identity/social-security number; a foundational identifier "
        "whose exposure enables broad identity fraud.",
    ),
    "API_KEY": (
        Severity.CRITICAL,
        "A live credential. Anyone who reads it can act as your system against "
        "the third-party service until it is rotated.",
    ),
    "AWS_KEY": (
        Severity.CRITICAL,
        "A cloud access key. Exposure can mean full account compromise and data "
        "exfiltration until rotated.",
    ),
    "JWT": (
        Severity.CRITICAL,
        "A bearer token. Whoever holds it is authenticated as the subject until "
        "it expires or is revoked.",
    ),
}

_DEFAULT = (
    Severity.MEDIUM,
    "A detected personal identifier. Personal data under the DPDP Act; review "
    "whether it should have reached a third-party provider.",
)


def classify(entity_type: str) -> tuple[Severity, str]:
    return _TABLE.get(entity_type, _DEFAULT)
