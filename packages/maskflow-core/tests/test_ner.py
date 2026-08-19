"""register_ner_recognizer() and the spaCy-optional degrade path -- new engine
surface introduced by this restructure (PERSON_NAME/DATE_OF_BIRTH used to be
hardcoded in core's ner.py; now any pack can register a spaCy label the same
way). The "label -> Span" dispatch is tested against a fake spaCy doc so it
doesn't depend on the real model's linguistic judgment; the spaCy-absent path
is tested by making `import spacy` genuinely fail.
"""

import sys
import warnings

import maskflow_core.ner as ner_module
import pytest
from maskflow_core.registry import register_ner_recognizer


class _FakeEnt:
    def __init__(self, label: str, text: str, start: int, end: int) -> None:
        self.label_ = label
        self.text = text
        self.start_char = start
        self.end_char = end


class _FakeDoc:
    def __init__(self, ents: list[_FakeEnt]) -> None:
        self.ents = ents


def test_register_ner_recognizer_dispatches_a_matching_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_ner_recognizer("TEST_LABEL", "TEST_PLACE", 0.7)
    fake_doc = _FakeDoc([_FakeEnt("TEST_LABEL", "Testville", 10, 19)])
    monkeypatch.setattr(ner_module, "_get_nlp", lambda: lambda text: fake_doc)

    spans = ner_module.detect_ner("I live in Testville today.")

    assert any(s.entity_type == "TEST_PLACE" and s.text == "Testville" for s in spans)


def test_register_ner_recognizer_ignores_unmapped_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    register_ner_recognizer("TEST_LABEL", "TEST_PLACE", 0.7)
    fake_doc = _FakeDoc([_FakeEnt("SOME_OTHER_LABEL", "Whatever", 0, 8)])
    monkeypatch.setattr(ner_module, "_get_nlp", lambda: lambda text: fake_doc)

    spans = ner_module.detect_ner("Whatever happens next.")

    assert spans == []


def test_ner_threshold_drops_low_confidence_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    register_ner_recognizer("TEST_LOW_LABEL", "TEST_LOW", 0.2, threshold=0.6)
    fake_doc = _FakeDoc([_FakeEnt("TEST_LOW_LABEL", "Something", 0, 9)])
    monkeypatch.setattr(ner_module, "_get_nlp", lambda: lambda text: fake_doc)

    spans = ner_module.detect_ner("Something happened.")

    assert spans == []


def test_get_nlp_warns_once_and_disables_ner_when_spacy_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_ner_recognizer("TEST_ABSENT_LABEL", "TEST_ABSENT", 0.7)
    ner_module._get_nlp.cache_clear()
    monkeypatch.setitem(sys.modules, "spacy", None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spans = ner_module.detect_ner("Some text that would otherwise be scanned.")

    assert spans == []
    spacy_warnings = [w for w in caught if "spaCy isn't installed" in str(w.message)]
    assert len(spacy_warnings) == 1

    ner_module._get_nlp.cache_clear()
