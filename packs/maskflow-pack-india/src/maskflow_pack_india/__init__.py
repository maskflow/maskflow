"""Registers MaskFlow's India-specific recognizers (AADHAAR, AADHAAR_MASKED,
PAN, GSTIN, IFSC, UPI_VPA) against maskflow-core on import. Importing this
package is the side effect that makes detect()/mask()/unmask() aware of
these types -- see maskflow_core.registry.register_pattern.

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

__all__: list[str] = []
