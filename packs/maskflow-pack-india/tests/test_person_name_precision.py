"""PERSON_NAME precision fixes: very common English words in the name
gazetteer (data/indian_names.py's _COMMON_ENGLISH_WORDS) and spaCy PERSON
entities made only of ID labels / Hinglish function words (__init__.py's
span_filter). All names below are illustrative, not real people's data.
"""

import maskflow_pack_india  # noqa: F401 -- import side effect registers PERSON_NAME
import pytest
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType
from maskflow_core.registry import NER_RECOGNIZERS
from maskflow_pack_india import _plausible_person_entity
from maskflow_pack_india.data.indian_names import TIER_COMMON, load_indian_names


def _names(text: str) -> list[str]:
    return [s.text for s in detect(text) if s.entity_type == PIIType.PERSON_NAME]


class TestCommonEnglishWords:
    @pytest.mark.parametrize("word", ["follow", "good", "one", "said", "amazing"])
    def test_demoted_to_the_needs_context_tier(self, word: str) -> None:
        assert load_indian_names()[word] == TIER_COMMON

    @pytest.mark.parametrize(
        "text",
        [
            "Follow-up on the refund request.",
            "Good morning, please help with my account.",
            "One more thing about the refund.",
        ],
    )
    def test_sentence_initial_common_word_is_not_a_name(self, text: str) -> None:
        assert _names(text) == []

    def test_common_word_still_detected_as_a_name_in_context(self) -> None:
        assert "Lucky" in " ".join(_names("My name is Lucky and I need help."))

    def test_real_name_after_a_demoted_word_is_still_detected(self) -> None:
        assert "Priya" in " ".join(_names("Follow-up from Priya about the refund."))


class TestSpacyEntityFilter:
    @pytest.mark.parametrize(
        "entity", ["GSTIN", "ABHA", "Mera Aadhaar", "Namaste Ji", "PAN", "और मेरा", "मेरा नाम"]
    )
    def test_label_and_function_word_entities_are_rejected(self, entity: str) -> None:
        assert _plausible_person_entity(entity) is False

    @pytest.mark.parametrize("entity", ["Priya Sharma", "Mera naam Priya", "Rahul", ""])
    def test_entities_with_any_other_word_are_kept(self, entity: str) -> None:
        assert _plausible_person_entity(entity) is True

    def test_filter_is_registered_on_the_live_spacy_mapping(self) -> None:
        assert NER_RECOGNIZERS["PERSON"].span_filter is _plausible_person_entity

    def test_hinglish_ticket_end_to_end(self) -> None:
        # Synthetic, checksum-valid Aadhaar and GSTIN.
        text = (
            "Namaste, main Priya Sharma hoon. Mera Aadhaar 2346 8907 6549 hai. "
            "GSTIN 27ABCPS1234F1ZX, ABHA 91-5520-3381-4467."
        )
        names = _names(text)
        assert "Priya Sharma" in names
        assert not any(
            label in name for name in names for label in ("Mera", "Aadhaar", "GSTIN", "ABHA")
        )
