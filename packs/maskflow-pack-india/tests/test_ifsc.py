import maskflow_pack_india  # noqa: F401 -- import side effect registers IFSC
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_hdfc(self) -> None:
        assert (PIIType.IFSC, "HDFC0001234") in _detected(
            "Please use IFSC code HDFC0001234 for the transfer."
        )

    def test_sbi(self) -> None:
        assert (PIIType.IFSC, "SBIN0000123") in _detected("Branch code: SBIN0000123.")

    def test_icici(self) -> None:
        assert (PIIType.IFSC, "ICIC0000456") in _detected("IFSC ICIC0000456 confirmed.")

    def test_paytm_payments_bank(self) -> None:
        assert (PIIType.IFSC, "PYTM0123456") in _detected("Bank branch code PYTM0123456 used.")

    def test_hindi_context(self) -> None:
        assert (PIIType.IFSC, "UTIB0002345") in _detected("आईएफएससी कोड UTIB0002345 दर्ज करें।")


class TestHardNegatives:
    def test_bank_code_not_in_bundled_list_rejected(self) -> None:
        found = _detected("Transfer code ZZZZ0123456 was not recognized by the gateway.")
        assert not any(t == PIIType.IFSC for t, _ in found)


class TestFormatVariants:
    def test_fifth_char_not_zero_never_matches(self) -> None:
        # HDFC1001234 -- 5th char '1' instead of the mandatory '0'.
        found = _detected("Transfer code HDFC1001234 was rejected.")
        assert not any(t == PIIType.IFSC for t, _ in found)

    def test_lowercase_never_matches(self) -> None:
        found = _detected("Transfer code hdfc0001234 was rejected.")
        assert not any(t == PIIType.IFSC for t, _ in found)

    def test_too_short_never_matches(self) -> None:
        found = _detected("Transfer code HDFC001234 was rejected.")
        assert not any(t == PIIType.IFSC for t, _ in found)
