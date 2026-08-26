"""Isolated tests for the Verhoeff (AADHAAR) and GSTIN checksum algorithms,
independent of regex/registration concerns. See checksums.py for the
algorithms themselves.
"""

from maskflow_pack_india.checksums import (
    gstin_checksum_char,
    gstin_is_valid,
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
