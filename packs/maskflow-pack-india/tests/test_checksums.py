"""Isolated tests for the Verhoeff (AADHAAR) and GSTIN checksum algorithms,
independent of regex/registration concerns. See checksums.py for the
algorithms themselves.
"""

from maskflow_pack_india.checksums import (
    gstin_checksum_char,
    gstin_is_valid,
    indian_passport_mrz_line2_is_valid,
    mrz_check_digit,
    mrz_line1_generate,
    mrz_line2_generate,
    verhoeff_generate,
    verhoeff_is_valid,
)


class TestVerhoeff:
    def test_published_reference_vector(self) -> None:
        # Wikipedia "Verhoeff algorithm" worked example: base "236" -> check
        # digit "3" -> full number "2363".
        assert verhoeff_generate("236") == "3"
        assert verhoeff_is_valid("2363") is True

    def test_corrupted_check_digit_is_invalid(self) -> None:
        assert verhoeff_is_valid("2364") is False

    def test_corrupted_interior_digit_is_invalid(self) -> None:
        assert verhoeff_is_valid("2373") is False

    def test_generated_12_digit_vectors_round_trip(self) -> None:
        for base11 in ("23456789012", "91234567890", "29999999999"):
            check = verhoeff_generate(base11)
            full = base11 + check
            assert verhoeff_is_valid(full)

    def test_single_digit_corruption_detected(self) -> None:
        base11 = "23456789012"
        full = base11 + verhoeff_generate(base11)
        for i in range(len(full)):
            original_digit = full[i]
            for replacement in "0123456789":
                if replacement == original_digit:
                    continue
                corrupted = full[:i] + replacement + full[i + 1 :]
                assert not verhoeff_is_valid(corrupted), (i, corrupted)

    def test_generated_16_digit_vid_vectors_round_trip(self) -> None:
        for base15 in ("234567890123456", "912345678901234"):
            check = verhoeff_generate(base15)
            assert verhoeff_is_valid(base15 + check)


class TestGstinChecksum:
    def test_generated_vectors_round_trip(self) -> None:
        # base14 = state(2) + a structurally-valid PAN(10) + entity(1) + 'Z'.
        for base14 in ("27ABCPE1234F1Z", "07AAACX9999K1Z", "33FGHPZ0001A2Z"):
            check = gstin_checksum_char(base14)
            full = base14 + check
            assert gstin_is_valid(full)

    def test_corrupted_check_char_is_invalid(self) -> None:
        base14 = "27ABCPE1234F1Z"
        check = gstin_checksum_char(base14)
        corrupted_check = "A" if check != "A" else "B"
        assert not gstin_is_valid(base14 + corrupted_check)

    def test_wrong_length_is_invalid(self) -> None:
        assert gstin_is_valid("27ABCPE1234F1Z") is False  # 14 chars, missing checksum
        assert gstin_is_valid("27ABCPE1234F1ZBB") is False  # 16 chars

    def test_non_alphabet_character_is_invalid_not_a_crash(self) -> None:
        assert gstin_is_valid("27abcpe1234f1zb") is False  # lowercase isn't in _GST_ALPHABET


class TestMrzCheckDigit:
    # ICAO Doc 9303 / Wikipedia "Machine-readable passport" worked example
    # (fictional "Utopia" passport, Anna Maria Eriksson) -- the standard
    # published reference vector for this algorithm:
    # line 2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
    _REFERENCE_LINE2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"

    def test_published_reference_vector_per_field(self) -> None:
        assert mrz_check_digit("L898902C3") == "6"  # document number
        assert mrz_check_digit("740812") == "2"  # date of birth
        assert mrz_check_digit("120415") == "9"  # date of expiry
        assert mrz_check_digit("ZE184226B<<<<<") == "1"  # personal number

    def test_published_reference_vector_full_line(self) -> None:
        assert indian_passport_mrz_line2_is_valid(self._REFERENCE_LINE2) is True

    def test_corrupted_document_number_check_digit_invalid(self) -> None:
        corrupted = "L898902C35UTO7408122F1204159ZE184226B<<<<<10"  # 6 -> 5
        assert indian_passport_mrz_line2_is_valid(corrupted) is False

    def test_corrupted_dob_check_digit_invalid(self) -> None:
        corrupted = "L898902C36UTO7408121F1204159ZE184226B<<<<<10"  # 2 -> 1
        assert indian_passport_mrz_line2_is_valid(corrupted) is False

    def test_corrupted_expiry_check_digit_invalid(self) -> None:
        corrupted = "L898902C36UTO7408122F1204158ZE184226B<<<<<10"  # 9 -> 8
        assert indian_passport_mrz_line2_is_valid(corrupted) is False

    def test_corrupted_composite_check_digit_invalid(self) -> None:
        corrupted = "L898902C36UTO7408122F1204159ZE184226B<<<<<11"  # 0 -> 1
        assert indian_passport_mrz_line2_is_valid(corrupted) is False

    def test_wrong_length_invalid(self) -> None:
        assert indian_passport_mrz_line2_is_valid("L898902C36UTO740812") is False

    def test_character_outside_mrz_alphabet_is_invalid_not_a_crash(self) -> None:
        corrupted = "l898902C36UTO7408122F1204159ZE184226B<<<<<10"  # lowercase 'l'
        assert indian_passport_mrz_line2_is_valid(corrupted) is False

    def test_generated_vectors_round_trip(self) -> None:
        for passport_no, dob, expiry, personal_no in (
            ("A1234567", "900101", "300101", "PN1234567"),
            ("B7654321", "851231", "281231", ""),
            ("M0000001", "700615", "351215", "AB<<12345"),
        ):
            line2 = mrz_line2_generate(passport_no, dob, expiry, personal_no)
            assert len(line2) == 44
            assert indian_passport_mrz_line2_is_valid(line2) is True

    def test_unused_personal_number_check_digit_of_filler_is_accepted(self) -> None:
        # ICAO 9303 Part 4: an issuer may write '<' instead of a computed
        # digit in the personal-number check-digit position when that field
        # is entirely unused. The composite check digit still covers
        # whatever character actually occupies that position.
        line2 = mrz_line2_generate("A1234567", "900101", "300101")
        passport_no, passport_check = line2[0:9], line2[9]
        dob, dob_check = line2[13:19], line2[19]
        expiry, expiry_check = line2[21:27], line2[27]
        personal_no = line2[28:42]
        composite_field = (
            passport_no
            + passport_check
            + dob
            + dob_check
            + expiry
            + expiry_check
            + personal_no
            + "<"
        )
        patched = line2[:42] + "<" + mrz_check_digit(composite_field)
        assert indian_passport_mrz_line2_is_valid(patched) is True

    def test_line1_generate_is_44_chars_and_regex_shaped(self) -> None:
        line1 = mrz_line1_generate("Sharma", "Rohit Kumar")
        assert len(line1) == 44
        assert line1.startswith("P<IND")
