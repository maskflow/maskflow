"""Registers MaskFlow's India-specific recognizers (AADHAAR, AADHAAR_MASKED,
PAN, GSTIN, IFSC, UPI_VPA, INDIAN_MOBILE, PIN_CODE, VOTER_ID,
INDIAN_PASSPORT, DRIVING_LICENCE, VEHICLE_REG, ABHA_NUMBER, ABHA_ADDRESS,
BANK_ACCOUNT_IN) against maskflow-core on import. Importing this package is
the side effect that makes detect()/mask()/unmask() aware of these types --
see maskflow_core.registry.register_pattern.

Context keywords are positive-only (English, Hindi/Devanagari, and Hinglish
transliterations) -- maskflow-core's context.apply_context_boost() has no
negative-context mechanism yet (CLAUDE.md's confidence formula documents one
as a target, but it isn't implemented in core), so "example/test/dummy"-style
suppression is out of scope for this pack until core grows that hook.
"""

from maskflow_core.registry import register_pattern

from . import patterns

register_pattern(
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
register_pattern(
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
register_pattern(
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

register_pattern(
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
register_pattern(
    "PAN",
    patterns.PAN_EMBEDDED_IN_GSTIN_RE,
    0.6,
    validator=patterns.validate_pan,
)

register_pattern(
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

register_pattern(
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

register_pattern(
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

register_pattern(
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

# All 28 states + 8 union territories (as of this pack's 2026-08 refresh) --
# a state/UT name next to a 6-digit number is as strong a signal for
# PIN_CODE as the word "pincode" itself.
_INDIAN_STATE_AND_UT_NAMES = (
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "andaman and nicobar",
    "chandigarh",
    "dadra and nagar haveli",
    "daman and diu",
    "delhi",
    "jammu and kashmir",
    "ladakh",
    "lakshadweep",
    "puducherry",
)

register_pattern(
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
    )
    + _INDIAN_STATE_AND_UT_NAMES,
)

register_pattern(
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

register_pattern(
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
# No context_keywords here -- register_pattern() stores CONTEXT_KEYWORDS per
# PIIType, not per pattern, so a second non-empty tuple for INDIAN_PASSPORT
# would overwrite the inline registration's keywords above. Doesn't matter
# for the MRZ block anyway: four independent ICAO check digits (0.97) clear
# DEFAULT_MIN_CONFIDENCE on their own, same as GSTIN needing none.
register_pattern(
    "INDIAN_PASSPORT",
    patterns.INDIAN_PASSPORT_MRZ_RE,
    0.6,
    validator=patterns.validate_indian_passport_mrz,
)

register_pattern(
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

register_pattern(
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

register_pattern(
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

register_pattern(
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

register_pattern(
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

__all__: list[str] = []
