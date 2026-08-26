import maskflow_pack_india  # noqa: F401 -- import side effect registers BANK_ACCOUNT_IN
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_account_number_context(self) -> None:
        assert (PIIType.BANK_ACCOUNT_IN, "011234567890123") in _detected(
            "Bank account number 011234567890123 for salary credit."
        )

    def test_a_c_no_context(self) -> None:
        assert (PIIType.BANK_ACCOUNT_IN, "098765432109") in _detected(
            "A/c no 098765432109 for the refund."
        )

    def test_hindi_context(self) -> None:
        assert (PIIType.BANK_ACCOUNT_IN, "011234567890123") in _detected(
            "बैंक खाता संख्या 011234567890123 दर्ज।"
        )

    def test_nine_digit_minimum_length(self) -> None:
        assert (PIIType.BANK_ACCOUNT_IN, "098765432") in _detected(
            "Account number 098765432 verified."
        )

    def test_eighteen_digit_maximum_length(self) -> None:
        assert (PIIType.BANK_ACCOUNT_IN, "098765432109876543") in _detected(
            "Account number 098765432109876543 verified."
        )


class TestContextRequired:
    def test_bare_number_without_context_is_dropped(self) -> None:
        found = _detected("Reference 011234567890123 was logged in the system.")
        assert not any(t == PIIType.BANK_ACCOUNT_IN for t, _ in found)


class TestHardNegatives:
    def test_document_full_of_invoice_and_order_and_tracking_numbers_produces_zero_detections(
        self,
    ) -> None:
        # None of these digit runs are Luhn-valid -- maskflow-sdk loads
        # pack-intl's CREDIT_CARD (any 13-19 digit run, Luhn-validated)
        # alongside this pack, and this test's "zero detections, period"
        # assertion must hold regardless of which other packs are loaded
        # in the same process.
        text = (
            "Invoice number 481027569301 was generated on schedule. "
            "Order ID 372615508192730 shipped via express courier. "
            "Tracking reference 918273645501298 was scanned at the depot."
        )
        assert detect(text) == []


class TestFormatVariants:
    def test_eight_digits_below_minimum_never_matches(self) -> None:
        found = _detected("Account number 12345678 was created.")
        assert not any(t == PIIType.BANK_ACCOUNT_IN for t, _ in found)

    def test_nineteen_digits_above_maximum_never_matches(self) -> None:
        found = _detected("Account number 1234567890123456789 was created.")
        assert not any(t == PIIType.BANK_ACCOUNT_IN for t, _ in found)
