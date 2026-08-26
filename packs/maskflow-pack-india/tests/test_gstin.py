import maskflow_pack_india  # noqa: F401 -- import side effect registers GSTIN/PAN
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> list:
    return detect(text)


def _pairs(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_generated_gstin(self) -> None:
        assert (PIIType.GSTIN, "27ABCPE1234F1ZB") in _pairs(
            "GSTIN registered for this business: 27ABCPE1234F1ZB."
        )

    def test_different_state_and_entity_number(self) -> None:
        assert (PIIType.GSTIN, "07AAACX9876K2ZH") in _pairs("GST no 07AAACX9876K2ZH filed.")

    def test_hindi_context(self) -> None:
        assert (PIIType.GSTIN, "33XYZHP4321Q1ZE") in _pairs("जीएसटी संख्या 33XYZHP4321Q1ZE दर्ज।")


class TestEmbeddedPanContainment:
    """CLAUDE.md: 'A valid GSTIN also emits the embedded PAN span; resolution
    handles containment.' PAN_EMBEDDED_IN_GSTIN_RE independently matches the
    PAN-shaped substring inside a GSTIN, producing a PAN candidate span that
    spanset.py's CONTAINS resolution then drops in favor of the longer,
    equally-validated GSTIN span -- exactly one span should survive.
    """

    def test_only_gstin_span_survives_not_a_duplicate_pan_span(self) -> None:
        spans = _detected("GSTIN registered for this business: 27ABCPE1234F1ZB.")
        matching = [s for s in spans if s.text == "27ABCPE1234F1ZB" or s.text == "ABCPE1234F"]
        assert len(matching) == 1
        assert matching[0].entity_type == PIIType.GSTIN
        assert matching[0].text == "27ABCPE1234F1ZB"

    def test_embedded_pan_pattern_does_independently_match_the_substring(self) -> None:
        # Confirms the candidate really is produced (and then loses
        # resolution) rather than never existing -- otherwise the test above
        # would trivially pass for the wrong reason.
        from maskflow_pack_india.patterns import PAN_EMBEDDED_IN_GSTIN_RE

        match = PAN_EMBEDDED_IN_GSTIN_RE.search("27ABCPE1234F1ZB")
        assert match is not None
        assert match.group(0) == "ABCPE1234F"


class TestInvalidChecksum:
    def test_bad_checksum_char_rejected(self) -> None:
        found = _pairs("Filing reference 27ABCPE1234F1ZA could not be matched.")
        assert not any(t == PIIType.GSTIN for t, _ in found)


class TestHardNegatives:
    def test_state_code_out_of_range_rejected(self) -> None:
        found = _pairs("Filing reference 99ABCPE1234F1ZB could not be matched.")
        assert not any(t == PIIType.GSTIN for t, _ in found)

    def test_state_code_zero_rejected(self) -> None:
        found = _pairs("Filing reference 00ABCPE1234F1ZB could not be matched.")
        assert not any(t == PIIType.GSTIN for t, _ in found)

    def test_missing_literal_z_rejected(self) -> None:
        # Position 14 must be the literal 'Z' -- the regex itself enforces
        # this, so a corrupted value there never even becomes a candidate.
        found = _pairs("Filing reference 27ABCPE1234F1YB could not be matched.")
        assert not any(t == PIIType.GSTIN for t, _ in found)

    def test_embedded_pan_with_bad_category_char_rejected(self) -> None:
        # 4th char of the embedded PAN ('D') isn't in the holder-category
        # set -- validate_gstin() reuses validate_pan() and must reject too.
        from maskflow_pack_india.checksums import gstin_checksum_char

        base14 = "27ABCDE1234F1Z"  # 'D' at PAN position 4 -- invalid category
        bad_gstin = base14 + gstin_checksum_char(base14)
        found = _pairs(f"Filing reference {bad_gstin} could not be matched.")
        assert not any(t == PIIType.GSTIN for t, _ in found)


class TestFormatVariants:
    def test_lowercase_never_matches(self) -> None:
        found = _pairs("Filing reference 27abcpe1234f1zb could not be matched.")
        assert not any(t == PIIType.GSTIN for t, _ in found)
