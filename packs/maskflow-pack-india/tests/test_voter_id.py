import maskflow_pack_india  # noqa: F401 -- import side effect registers VOTER_ID
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_voter_id_card_number(self) -> None:
        assert (PIIType.VOTER_ID, "ABC1234567") in _detected(
            "Voter ID card number ABC1234567 on file."
        )

    def test_epic_context(self) -> None:
        assert (PIIType.VOTER_ID, "XYZ7654321") in _detected("EPIC no. XYZ7654321 verified.")

    def test_hindi_context(self) -> None:
        assert (PIIType.VOTER_ID, "ABC1234567") in _detected("मतदाता पहचान पत्र ABC1234567 सत्यापित।")

    def test_detected_without_context_keyword(self) -> None:
        # base 0.55 already clears the 0.5 default threshold on shape alone
        # -- context isn't load-bearing for VOTER_ID.
        assert (PIIType.VOTER_ID, "ABC1234567") in _detected("Reference: ABC1234567 attached.")


class TestFormatVariants:
    def test_two_letters_instead_of_three_never_matches(self) -> None:
        found = _detected("Voter ID AB1234567 registered.")
        assert not any(t == PIIType.VOTER_ID for t, _ in found)

    def test_six_digits_instead_of_seven_never_matches(self) -> None:
        found = _detected("Voter ID ABC123456 registered.")
        assert not any(t == PIIType.VOTER_ID for t, _ in found)

    def test_lowercase_never_matches(self) -> None:
        found = _detected("Voter ID abc1234567 registered.")
        assert not any(t == PIIType.VOTER_ID for t, _ in found)
