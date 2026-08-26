import maskflow_pack_india  # noqa: F401 -- import side effect registers PIN_CODE
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_state_name_context(self) -> None:
        assert (PIIType.PIN_CODE, "560001") in _detected(
            "Ship the package to Bengaluru, Karnataka - 560001."
        )

    def test_pincode_keyword_context(self) -> None:
        assert (PIIType.PIN_CODE, "110001") in _detected(
            "Pincode: 110001 for the New Delhi office."
        )

    def test_hindi_context(self) -> None:
        assert (PIIType.PIN_CODE, "400001") in _detected("पिन कोड 400001 दर्ज करें।")


class TestContextRequired:
    def test_bare_six_digit_number_without_context_is_dropped(self) -> None:
        found = _detected("Order reference 560001 was updated in the system.")
        assert not any(t == PIIType.PIN_CODE for t, _ in found)


class TestHardNegatives:
    def test_document_full_of_invoice_and_order_and_tracking_numbers_produces_zero_detections(
        self,
    ) -> None:
        text = (
            "Invoice number 481027 was generated on schedule. "
            "Order ID 372615 shipped via express courier. "
            "Batch reference 550198 was archived for the quarter."
        )
        assert detect(text) == []


class TestFormatVariants:
    def test_zone_9_first_digit_never_matches(self) -> None:
        # India Post's postal zone 9 (army post offices) is excluded --
        # even with "postal code" context present, first digit 9 never
        # matches the [1-8] class.
        found = _detected("Postal code 912345 for the location.")
        assert not any(t == PIIType.PIN_CODE for t, _ in found)

    def test_five_digit_number_never_matches(self) -> None:
        found = _detected("Pincode: 56001 for the office.")
        assert not any(t == PIIType.PIN_CODE for t, _ in found)
