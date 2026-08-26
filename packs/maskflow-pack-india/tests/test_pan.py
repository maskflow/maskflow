import maskflow_pack_india  # noqa: F401 -- import side effect registers PAN
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_category_p_individual(self) -> None:
        assert (PIIType.PAN, "ABCPE1234F") in _detected("PAN card number: ABCPE1234F.")

    def test_category_c_company(self) -> None:
        assert (PIIType.PAN, "AAACX9876K") in _detected("PAN: AAACX9876K on file.")

    def test_category_h_huf(self) -> None:
        assert (PIIType.PAN, "XYZHP4321Q") in _detected("PAN number XYZHP4321Q submitted.")

    def test_category_f_firm(self) -> None:
        assert (PIIType.PAN, "MNOFA7654B") in _detected("Firm PAN MNOFA7654B registered.")

    def test_category_a_aop(self) -> None:
        assert (PIIType.PAN, "PQRAT2345C") in _detected("PAN no PQRAT2345C for the trust.")

    def test_hindi_context(self) -> None:
        assert (PIIType.PAN, "AAACX9876K") in _detected("पैन कार्ड AAACX9876K है।")

    def test_detected_without_context_keyword(self) -> None:
        # base 0.6 + structural-check bump to 0.85 already clears the 0.5
        # default threshold on its own -- context isn't load-bearing for PAN.
        assert (PIIType.PAN, "ABCPE1234F") in _detected("Reference: ABCPE1234F attached.")


class TestHardNegatives:
    def test_fourth_char_outside_category_set_rejected(self) -> None:
        # 'D' is not in {P,C,H,F,A,T,B,L,J,G}.
        found = _detected("Reference code ABCDE1234F was logged for audit.")
        assert not any(t == PIIType.PAN for t, _ in found)

    def test_lowercase_never_matches(self) -> None:
        found = _detected("Reference code abcpe1234f was logged for audit.")
        assert not any(t == PIIType.PAN for t, _ in found)

    def test_wrong_digit_count_never_matches(self) -> None:
        found = _detected("Reference code ABCPE123F was logged for audit.")
        assert not any(t == PIIType.PAN for t, _ in found)


class TestFormatVariants:
    def test_embedded_in_gstin_not_matched_by_standalone_pan_pattern(self) -> None:
        # PAN_RE excludes alnum neighbors on both sides, so it does NOT
        # independently fire on the PAN embedded inside a GSTIN -- that's
        # PAN_EMBEDDED_IN_GSTIN_RE's job, exercised in test_gstin.py.
        from maskflow_pack_india.patterns import PAN_RE

        assert PAN_RE.search("27ABCPE1234F1ZB") is None
