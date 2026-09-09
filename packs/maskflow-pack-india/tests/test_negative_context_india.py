"""Negative-context suppression (#63): an illustrative-value marker
("example", "sample", "udaharan", "फर्जी", ...) within 40 chars of a
candidate lowers its confidence by 0.3, enough to pull the shape-only,
context-gated types back under threshold. Checksum-validated identifiers
stay above it -- masking a fake-but-valid number is harmless.
"""

import maskflow_pack_india  # noqa: F401 -- import side effect registers the pack + negative keywords
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _types(text: str) -> set[PIIType]:
    return {s.entity_type for s in detect(text)}


class TestSuppressesContextGatedTypes:
    def test_pin_code_with_state_name_but_example_marker_is_dropped(self) -> None:
        # "Karnataka" alone would clear PIN_CODE's bar (0.3 + 0.4 boost).
        assert PIIType.PIN_CODE in _types("Ship to Bengaluru, Karnataka - 560001.")
        assert PIIType.PIN_CODE not in _types(
            "Sample record -- Bengaluru, Karnataka - 560001."
        )

    def test_indian_mobile_with_keyword_but_sample_marker_is_dropped(self) -> None:
        assert PIIType.INDIAN_MOBILE in _types("My mobile number is 9876543211, call anytime.")
        assert PIIType.INDIAN_MOBILE not in _types(
            "Sample data -- mobile number 9876543211 -- do not dial."
        )

    def test_bank_account_with_keyword_but_dummy_marker_is_dropped(self) -> None:
        assert PIIType.BANK_ACCOUNT_IN in _types("Credit account number 123456789012.")
        assert PIIType.BANK_ACCOUNT_IN not in _types(
            "Dummy account number 123456789012 on the specimen form."
        )


class TestLanguageCoverage:
    def test_devanagari_example_marker_suppresses(self) -> None:
        assert PIIType.PIN_CODE in _types("पिन कोड 400001 दर्ज करें।")
        assert PIIType.PIN_CODE not in _types("उदाहरण के लिए पिन कोड 400001 दर्ज करें।")

    def test_hinglish_farzi_marker_suppresses(self) -> None:
        assert PIIType.INDIAN_MOBILE not in _types(
            "yeh ek farzi number hai: mobile number 9876543211"
        )


class TestValidatedIdentifiersSurvive:
    def test_checksum_valid_aadhaar_near_example_is_still_masked(self) -> None:
        # 234567890124 is Verhoeff-valid; validator -> 0.9, "aadhaar" boosts,
        # -0.3 still leaves it well above threshold. Deliberate: a fake but
        # shape-valid number being masked costs nothing.
        assert PIIType.AADHAAR in _types(
            "For example, an Aadhaar number looks like 234567890124."
        )


class TestNoFalseSuppression:
    def test_ordinary_text_mentioning_a_person_is_unaffected(self) -> None:
        # "example" appears, but not within 40 chars of the number.
        text = (
            "Here is an example of the report format we discussed at length last week. "
            "Contact number 9876543211, mobile number on file."
        )
        assert PIIType.INDIAN_MOBILE in _types(text)
