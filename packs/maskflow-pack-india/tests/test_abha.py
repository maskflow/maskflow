import maskflow_pack_india  # noqa: F401 -- import side effect registers ABHA_NUMBER/ABHA_ADDRESS
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestAbhaNumberValid:
    def test_hyphenated_with_context(self) -> None:
        assert (PIIType.ABHA_NUMBER, "12-3456-7890-1234") in _detected(
            "ABHA number 12-3456-7890-1234 linked to health records."
        )

    def test_unspaced_with_health_id_context(self) -> None:
        # Last digit deliberately chosen so this string is NOT also
        # Luhn-valid -- maskflow-sdk loads pack-intl's CREDIT_CARD (which
        # matches any 13-19 digit run, Luhn-validated) alongside this pack,
        # and a validated CREDIT_CARD span would win overlap resolution
        # over an unvalidated ABHA_NUMBER span on the same text.
        assert (PIIType.ABHA_NUMBER, "34567890123450") in _detected(
            "Your health ID 34567890123450 is now active."
        )

    def test_ayushman_context(self) -> None:
        assert (PIIType.ABHA_NUMBER, "45678901234560") in _detected(
            "Ayushman Bharat health account 45678901234560 created."
        )

    def test_hindi_context(self) -> None:
        assert (PIIType.ABHA_NUMBER, "56789012345678") in _detected("आभा नंबर 56789012345678 सक्रिय।")


class TestAbhaNumberContextRequired:
    def test_bare_number_without_context_is_dropped(self) -> None:
        found = _detected("Reference number 12-3456-7890-1234 was logged.")
        assert not any(t == PIIType.ABHA_NUMBER for t, _ in found)


class TestAbhaNumberHardNegatives:
    def test_document_full_of_invoice_and_order_and_tracking_numbers_produces_zero_detections(
        self,
    ) -> None:
        text = (
            "Invoice number 48102756930148 was generated on schedule. "
            "Order ID 37261550819273 shipped via express courier. "
            "Tracking reference 91827364550129 was scanned at the depot."
        )
        assert detect(text) == []


class TestAbhaNumberFormatVariants:
    def test_inconsistent_separators_never_matches(self) -> None:
        found = _detected("ABHA number 12-3456 7890-1234 linked to health records.")
        assert not any(t == PIIType.ABHA_NUMBER for t, _ in found)

    def test_thirteen_digits_never_matches(self) -> None:
        found = _detected("ABHA number 1234567890123 was verified for the health record.")
        assert not any(t == PIIType.ABHA_NUMBER for t, _ in found)


class TestAbhaAddressValid:
    def test_abdm_domain(self) -> None:
        assert (PIIType.ABHA_ADDRESS, "priya.sharma@abdm") in _detected(
            "ABHA address priya.sharma@abdm used for linking."
        )

    def test_sbx_sandbox_domain(self) -> None:
        assert (PIIType.ABHA_ADDRESS, "rahul.kumar@sbx") in _detected(
            "Health ID rahul.kumar@sbx registered."
        )


class TestAbhaAddressHardNegatives:
    def test_domain_not_on_the_known_list_rejected(self) -> None:
        found = _detected("Health ID rahul.k@randomclinic was rejected as invalid.")
        assert not any(t == PIIType.ABHA_ADDRESS for t, _ in found)

    def test_domain_that_is_a_upi_handle_not_an_abha_domain_rejected(self) -> None:
        # "paytm" is a real UPI PSP handle but not an ABHA domain -- must be
        # classified as UPI_VPA (if at all), never ABHA_ADDRESS.
        found = _detected("Health ID priya.sharma@paytm was rejected as invalid.")
        assert not any(t == PIIType.ABHA_ADDRESS for t, _ in found)
