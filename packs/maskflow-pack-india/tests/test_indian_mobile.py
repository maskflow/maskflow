import maskflow_pack_india  # noqa: F401 -- import side effect registers INDIAN_MOBILE
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_plus_91_prefix_no_context_needed(self) -> None:
        assert (PIIType.INDIAN_MOBILE, "+919876543210") in _detected(
            "Reach the delivery agent at +919876543210 for updates."
        )

    def test_zero_trunk_prefix_no_context_needed(self) -> None:
        assert (PIIType.INDIAN_MOBILE, "09123456789") in _detected(
            "Alternate contact: 09123456789."
        )

    def test_hyphenated_plus_91_prefix(self) -> None:
        assert (PIIType.INDIAN_MOBILE, "+91-9988776655") in _detected(
            "WhatsApp me on +91-9988776655 for the invoice."
        )

    def test_bare_number_with_context_keyword(self) -> None:
        assert (PIIType.INDIAN_MOBILE, "9876543211") in _detected(
            "My mobile number is 9876543211, call anytime."
        )

    def test_hindi_context(self) -> None:
        assert (PIIType.INDIAN_MOBILE, "9876543212") in _detected("मेरा मोबाइल नंबर 9876543212 है।")


class TestContextRequired:
    def test_bare_number_without_context_is_dropped(self) -> None:
        found = _detected("Reference 9876543210 was logged in the ticket.")
        assert not any(t == PIIType.INDIAN_MOBILE for t, _ in found)


class TestHardNegatives:
    def test_document_full_of_invoice_and_order_and_tracking_numbers_produces_zero_detections(
        self,
    ) -> None:
        # 10-digit numbers, first digit 6-9, no phone/mobile/contact keyword
        # anywhere nearby -- per CLAUDE.md, this must produce zero findings.
        text = (
            "Invoice 9081726354 was generated on schedule. "
            "Order ID 8172635940 shipped via express courier. "
            "Tracking reference 7263594081 was scanned at the depot."
        )
        assert detect(text) == []


class TestFormatVariants:
    def test_first_digit_outside_6_to_9_never_matches(self) -> None:
        found = _detected("Contact 5876543210 was logged for the wrong department.")
        assert not any(t == PIIType.INDIAN_MOBILE for t, _ in found)

    def test_nine_digit_number_never_matches(self) -> None:
        found = _detected("My mobile number is 987654321, call anytime.")
        assert not any(t == PIIType.INDIAN_MOBILE for t, _ in found)
