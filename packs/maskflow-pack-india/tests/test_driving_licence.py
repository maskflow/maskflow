import maskflow_pack_india  # noqa: F401 -- import side effect registers DRIVING_LICENCE
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_unspaced(self) -> None:
        assert (PIIType.DRIVING_LICENCE, "MH1420110012345") in _detected(
            "Driving licence number MH1420110012345 valid till 2030."
        )

    def test_spaced(self) -> None:
        assert (PIIType.DRIVING_LICENCE, "KA05 2015 0098765") in _detected(
            "DL no. KA05 2015 0098765 submitted for verification."
        )

    def test_hindi_context(self) -> None:
        assert (PIIType.DRIVING_LICENCE, "TN0919990012345") in _detected(
            "ड्राइविंग लाइसेंस TN0919990012345 सत्यापित।"
        )

    def test_detected_without_context_keyword(self) -> None:
        # base 0.5 + state-code structural bump to 0.85 already clears the
        # 0.5 default threshold on its own -- context isn't load-bearing.
        assert (PIIType.DRIVING_LICENCE, "MH1420110012345") in _detected(
            "Reference: MH1420110012345 attached."
        )


class TestHardNegatives:
    def test_state_code_not_a_real_rto_code_rejected(self) -> None:
        found = _detected("Driving licence ZZ1420110012345 valid till 2030.")
        assert not any(t == PIIType.DRIVING_LICENCE for t, _ in found)


class TestFormatVariants:
    def test_inconsistent_separators_never_matches(self) -> None:
        # Space before the year, hyphen before the serial -- the \2
        # backreference requires both gaps to match.
        found = _detected("Driving licence MH14 2011-0012345 valid till 2030.")
        assert not any(t == PIIType.DRIVING_LICENCE for t, _ in found)

    def test_year_outside_19xx_20xx_never_matches(self) -> None:
        found = _detected("Driving licence MH1421110012345 valid till 2030.")
        assert not any(t == PIIType.DRIVING_LICENCE for t, _ in found)

    def test_six_digit_serial_never_matches(self) -> None:
        # One digit short of the required 7-digit serial.
        found = _detected("Driving licence MH142011001234 valid till 2030.")
        assert not any(t == PIIType.DRIVING_LICENCE for t, _ in found)
