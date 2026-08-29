"""Strategy.SURROGATE generators: every registered India type produces a
fresh, format/checksum-valid fake value (checked against the pack's OWN
validate_*()/regex, mirroring generate.py's self_check() discipline for the
benchmark corpus), and the full mask_with_policy()/unmask() round trip works
end to end with SURROGATE selected as the default strategy.
"""

from __future__ import annotations

import random

import maskflow_pack_india  # noqa: F401 -- import side effect: registers surrogates
from maskflow_core.masking import mask_with_policy, unmask
from maskflow_core.policy import MaskPolicy
from maskflow_core.registry import SURROGATE_GENERATORS
from maskflow_core.strategies import Strategy
from maskflow_pack_india import patterns, surrogates
from maskflow_pack_india.checksums import indian_passport_mrz_line2_is_valid

_ALL_TYPES = (
    "AADHAAR",
    "AADHAAR_MASKED",
    "PAN",
    "GSTIN",
    "IFSC",
    "UPI_VPA",
    "INDIAN_MOBILE",
    "PIN_CODE",
    "VOTER_ID",
    "INDIAN_PASSPORT",
    "DRIVING_LICENCE",
    "VEHICLE_REG",
    "ABHA_NUMBER",
    "ABHA_ADDRESS",
    "BANK_ACCOUNT_IN",
    "PERSON_NAME",
    "INDIAN_ADDRESS",
)


def test_every_india_type_has_a_registered_generator() -> None:
    registered = {t.value for t in SURROGATE_GENERATORS}
    assert set(_ALL_TYPES) <= registered


class TestGeneratorOutputIsValid:
    def test_aadhaar_uid_and_vid_shapes(self) -> None:
        rng = random.Random(1)
        uid = surrogates.surrogate_aadhaar("2345 6789 0124", rng)
        assert patterns.validate_aadhaar(uid) is not None
        assert len(uid.replace(" ", "").replace("-", "")) == 12

        vid = surrogates.surrogate_aadhaar("2345678901234565", rng)
        assert patterns.validate_aadhaar(vid) is not None
        assert len(vid.replace(" ", "").replace("-", "")) == 16

    def test_aadhaar_masked_shape(self) -> None:
        out = surrogates.surrogate_aadhaar_masked("XXXX XXXX 9012", random.Random(2))
        assert patterns.AADHAAR_MASKED_RE.fullmatch(out)

    def test_pan(self) -> None:
        out = surrogates.surrogate_pan("KFRBX4755U", random.Random(3))
        assert patterns.validate_pan(out) is not None

    def test_gstin(self) -> None:
        out = surrogates.surrogate_gstin("29ABCDE1234F1Z5", random.Random(4))
        assert patterns.validate_gstin(out) is not None

    def test_ifsc(self) -> None:
        out = surrogates.surrogate_ifsc("SBIN0001234", random.Random(5))
        assert patterns.validate_ifsc(out) is not None

    def test_upi_vpa(self) -> None:
        out = surrogates.surrogate_upi_vpa("someone@paytm", random.Random(6))
        assert patterns.validate_upi_vpa(out) is not None

    def test_indian_mobile_preserves_prefix_style(self) -> None:
        rng = random.Random(7)
        assert surrogates.surrogate_indian_mobile("+919876543210", rng).startswith("+91")
        assert surrogates.surrogate_indian_mobile("08596948701", rng).startswith("0")
        bare = surrogates.surrogate_indian_mobile("9876543210", rng)
        assert patterns.validate_indian_mobile(bare) is not None
        assert bare[0] in "6789"

    def test_pin_code_shape(self) -> None:
        out = surrogates.surrogate_pin_code("232307", random.Random(8))
        assert patterns.PIN_CODE_RE.fullmatch(out)
        assert out[0] in "12345678"

    def test_voter_id_shape(self) -> None:
        out = surrogates.surrogate_voter_id("ABC1234567", random.Random(9))
        assert patterns.VOTER_ID_RE.fullmatch(out)

    def test_indian_passport_inline_shape(self) -> None:
        out = surrogates.surrogate_indian_passport("K1234567", random.Random(10))
        assert patterns.INDIAN_PASSPORT_RE.fullmatch(out)

    def test_indian_passport_mrz_shape(self) -> None:
        original = (
            "P<INDDOE<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
            "K12345670IND9001019M3001013<<<<<<<<<<<<<<02"
        )
        out = surrogates.surrogate_indian_passport(original, random.Random(11))
        line1, line2 = out.split("\n")
        assert line1.startswith("P<IND")
        assert indian_passport_mrz_line2_is_valid(line2)

    def test_driving_licence(self) -> None:
        out = surrogates.surrogate_driving_licence("MH1220110012345", random.Random(12))
        assert patterns.validate_driving_licence(out) is not None

    def test_vehicle_reg(self) -> None:
        out = surrogates.surrogate_vehicle_reg("MH12AB1234", random.Random(13))
        assert patterns.validate_vehicle_reg(out) is not None

    def test_abha_number_shape(self) -> None:
        out = surrogates.surrogate_abha_number("12-3456-7890-1234", random.Random(14))
        assert patterns.ABHA_NUMBER_RE.fullmatch(out)

    def test_abha_address(self) -> None:
        out = surrogates.surrogate_abha_address("someone@abdm", random.Random(15))
        assert patterns.validate_abha_address(out) is not None

    def test_bank_account_preserves_length(self) -> None:
        out = surrogates.surrogate_bank_account("43594822053786", random.Random(16))
        assert out.isdigit()
        assert len(out) == len("43594822053786")

    def test_person_name_preserves_word_count(self) -> None:
        out = surrogates.surrogate_person_name("Achalraj Kuvin", random.Random(17))
        assert len(out.split()) == 2
        assert all(w[0].isupper() for w in out.split())

    def test_indian_address_shape(self) -> None:
        out = surrogates.surrogate_indian_address("Phase 837B, Montreal Colony", random.Random(18))
        assert patterns.INDIAN_ADDRESS_UNIT_MARKER_RE.search(out)


def test_round_trip_with_surrogate_strategy() -> None:
    text = (
        "PERSONAL LOAN APPLICATION\n"
        "Applicant Name: Achalraj Kuvin\n"
        "PAN: KFRBX4755U\n"
        "Aadhaar Number: 5781-8936-3756\n"
        "Bank Account Number: 43594822053786\n"
        "IFSC Code: UTKS0W8L225\n"
        "Mobile Number: 08596948701\n"
    )
    result = mask_with_policy(text, policy=MaskPolicy(default_strategy=Strategy.SURROGATE))

    for original in (
        "Achalraj Kuvin",
        "KFRBX4755U",
        "5781-8936-3756",
        "43594822053786",
        "UTKS0W8L225",
        "08596948701",
    ):
        assert original not in result.masked_text

    # Simulate an LLM echoing the masked text back verbatim.
    restored = unmask(result.masked_text, result.mapping)
    assert restored == text
