import maskflow_pack_india  # noqa: F401 -- import side effect registers VEHICLE_REG
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_unspaced(self) -> None:
        assert (PIIType.VEHICLE_REG, "MH12AB1234") in _detected(
            "Vehicle registration number MH12AB1234 on file."
        )

    def test_hyphenated(self) -> None:
        assert (PIIType.VEHICLE_REG, "KA-05-MJ-1234") in _detected(
            "Car number KA-05-MJ-1234 was towed."
        )

    def test_single_digit_rto_code(self) -> None:
        assert (PIIType.VEHICLE_REG, "DL1CD5678") in _detected("Vehicle no DL1CD5678 registered.")

    def test_hindi_context(self) -> None:
        assert (PIIType.VEHICLE_REG, "TN09CD5678") in _detected("गाड़ी नंबर TN09CD5678 दर्ज।")

    def test_detected_without_context_keyword(self) -> None:
        assert (PIIType.VEHICLE_REG, "MH12AB1234") in _detected("Reference: MH12AB1234 attached.")


class TestHardNegatives:
    def test_state_code_not_a_real_rto_code_rejected(self) -> None:
        found = _detected("Vehicle number ZZ12AB1234 parked outside.")
        assert not any(t == PIIType.VEHICLE_REG for t, _ in found)


class TestFormatVariants:
    def test_three_digit_rto_code_never_matches(self) -> None:
        found = _detected("Vehicle number MH123AB1234 parked outside.")
        assert not any(t == PIIType.VEHICLE_REG for t, _ in found)

    def test_three_digit_serial_never_matches(self) -> None:
        found = _detected("Vehicle number MH12AB123 parked outside.")
        assert not any(t == PIIType.VEHICLE_REG for t, _ in found)
