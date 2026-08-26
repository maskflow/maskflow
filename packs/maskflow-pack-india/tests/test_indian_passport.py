import maskflow_pack_india  # noqa: F401 -- import side effect registers INDIAN_PASSPORT
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType
from maskflow_pack_india.checksums import mrz_line1_generate, mrz_line2_generate


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


def _mrz_block(passport_no: str, dob: str, expiry: str, personal_no: str = "") -> str:
    return (
        mrz_line1_generate("SHARMA", "ROHIT")
        + "\n"
        + mrz_line2_generate(passport_no, dob, expiry, personal_no)
    )


class TestInlineNumberValid:
    def test_basic_number(self) -> None:
        assert (PIIType.INDIAN_PASSPORT, "A1234567") in _detected("Passport number: A1234567.")

    def test_hindi_context(self) -> None:
        assert (PIIType.INDIAN_PASSPORT, "M9876543") in _detected("पासपोर्ट नंबर M9876543 दर्ज।")

    def test_letter_at_upper_end_of_range(self) -> None:
        # 'Y' is the highest letter MEA issues (Q/X/Z are excluded).
        assert (PIIType.INDIAN_PASSPORT, "Y1234567") in _detected("Passport no Y1234567 submitted.")


class TestInlineNumberFormatVariants:
    def test_excluded_letter_q_never_matches(self) -> None:
        found = _detected("Passport number Q1234567 issued.")
        assert not any(t == PIIType.INDIAN_PASSPORT for t, _ in found)

    def test_excluded_letter_x_never_matches(self) -> None:
        found = _detected("Passport number X1234567 issued.")
        assert not any(t == PIIType.INDIAN_PASSPORT for t, _ in found)

    def test_excluded_letter_z_never_matches(self) -> None:
        found = _detected("Passport number Z1234567 issued.")
        assert not any(t == PIIType.INDIAN_PASSPORT for t, _ in found)

    def test_leading_zero_after_letter_never_matches(self) -> None:
        # Second character must be [1-9], never 0.
        found = _detected("Passport number A0123456 issued.")
        assert not any(t == PIIType.INDIAN_PASSPORT for t, _ in found)


class TestMrzValid:
    def test_generated_mrz_block_is_detected_as_one_high_confidence_span(self) -> None:
        block = _mrz_block("A1234567", "900101", "300101", "PN1234567")
        spans = detect(f"Extracted from scan:\n{block}")
        matching = [s for s in spans if s.entity_type == PIIType.INDIAN_PASSPORT]
        assert len(matching) == 1
        assert matching[0].text == block
        assert matching[0].validated is True
        assert matching[0].score >= 0.95

    def test_mrz_block_without_optional_personal_number(self) -> None:
        block = _mrz_block("B7654321", "851231", "281231")
        spans = detect(f"Extracted from scan:\n{block}")
        matching = [s for s in spans if s.entity_type == PIIType.INDIAN_PASSPORT]
        assert len(matching) == 1
        assert matching[0].text == block


class TestMrzInvalidChecksum:
    def test_corrupted_composite_check_digit_drops_the_mrz_span_but_not_the_inline_number(
        self,
    ) -> None:
        # Mirrors test_gstin.py's TestEmbeddedPanContainment: the MRZ
        # composite checksum fails, so no MRZ span is emitted -- but the
        # document-number field is itself a structurally valid inline
        # INDIAN_PASSPORT number, so it correctly still fires on its own
        # (a correct detection, not a false positive).
        good_block = _mrz_block("B7654321", "851231", "281231")
        corrupted_last_char = "0" if good_block[-1] != "0" else "1"
        bad_block = good_block[:-1] + corrupted_last_char
        text = f"Extracted from scan:\n{bad_block}"

        found = _detected(text)
        assert not any("\n" in value for _entity, value in found)  # no full MRZ span
        assert (PIIType.INDIAN_PASSPORT, "B7654321") in found  # inline number still valid


class TestMrzFormatVariants:
    def test_non_indian_nationality_never_matches(self) -> None:
        # Scoped to Indian passports only -- a UTO-nationality MRZ block
        # (this pack's own checksum test vector) must not match.
        block = (
            "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n"
            "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
        )
        found = _detected(f"Extracted from scan:\n{block}")
        assert not any("\n" in value for _entity, value in found)
