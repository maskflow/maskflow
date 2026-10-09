"""PERSON_NAME for names written in Devanagari script (patterns.py's
PERSON_NAME_DEVANAGARI_* patterns). Before these existed a name like
"प्रिया शर्मा" was never detected: the L1 gazetteer is romanized-only and its
capitalisation gate can't pass for a script with no case. All names below are
illustrative, not real people's data.
"""

import maskflow_pack_india  # noqa: F401 -- import side effect registers PERSON_NAME
import pytest
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType
from maskflow_core.masking import mask, unmask


def _names(text: str) -> list[str]:
    return [s.text for s in detect(text) if s.entity_type == PIIType.PERSON_NAME]


class TestNameLabel:
    def test_self_introduction_stops_before_the_copula(self) -> None:
        assert _names("नमस्ते, मेरा नाम प्रिया शर्मा है।") == ["प्रिया शर्मा"]

    def test_copula_before_the_name(self) -> None:
        assert _names("मेरा नाम है अमित") == ["अमित"]

    def test_form_field_with_colon(self) -> None:
        assert _names("नाम: रमेश चंद्र वर्मा") == ["रमेश चंद्र वर्मा"]

    def test_form_field_with_hyphen(self) -> None:
        assert _names("आवेदक का नाम - सुनीता देवी") == ["सुनीता देवी"]

    def test_run_stops_at_a_conjunction(self) -> None:
        assert _names("मेरा नाम प्रिया शर्मा और मेरा आधार नंबर नीचे है") == ["प्रिया शर्मा"]


class TestHonorific:
    def test_shri(self) -> None:
        assert _names("श्री रमेश कुमार ने शिकायत की") == ["रमेश कुमार"]

    def test_shrimati_wins_over_shri_and_ji_is_not_part_of_the_name(self) -> None:
        assert _names("श्रीमती सुनीता देवी जी से बात हुई") == ["सुनीता देवी"]

    def test_doctor_with_and_without_dot(self) -> None:
        assert _names("डॉ. अनिल गुप्ता और डॉ अनिल गुप्ता") == ["अनिल गुप्ता", "अनिल गुप्ता"]

    def test_relational_form_style(self) -> None:
        assert _names("पुत्र श्री सुरेश कुमार") == ["सुरेश कुमार"]


class TestNegatives:
    def test_plain_sentence(self) -> None:
        assert _names("कृपया अपना रिफंड स्टेटस बताइए।") == []

    def test_name_label_followed_by_a_stopword(self) -> None:
        assert _names("किस नाम से खाता है?") == []

    def test_name_label_followed_by_digits(self) -> None:
        assert _names("नाम: 12345") == []


class TestHardNegatives:
    def test_jai_shri_ram_greeting(self) -> None:
        assert _names("जय श्री राम") == []

    def test_shri_as_the_start_of_a_longer_word(self) -> None:
        assert _names("श्रीनगर जाना है") == []

    def test_relational_word_in_running_prose(self) -> None:
        assert _names("उनकी पत्नी बहुत अच्छी हैं") == []


class TestKnownLimitations:
    """Documented in patterns.py. xfail(strict=True) so a future fix shows up
    as XPASS and the limitation note gets updated."""

    @pytest.mark.xfail(strict=True, reason="no structural cue before a bare Devanagari name")
    def test_bare_name_without_a_cue(self) -> None:
        assert _names("प्रिया शर्मा ने कॉल किया") == ["प्रिया शर्मा"]

    @pytest.mark.xfail(strict=True, reason="a verb right after a name label reads as a name")
    def test_verb_after_name_label(self) -> None:
        assert _names("मेरा नाम बदलना है") == []


def test_round_trip_is_exact() -> None:
    text = "नमस्ते, मेरा नाम प्रिया शर्मा है। श्रीमती सुनीता देवी जी से बात हुई।"
    result = mask(text)
    assert "प्रिया" not in result.masked_text
    assert "सुनीता" not in result.masked_text
    assert unmask(result.masked_text, result.mapping) == text
