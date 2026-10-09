"""What `import maskflow` actually registers, and the README Quickstart.

Both packs register PERSON_NAME, and the last registration wins for its
context keywords and spaCy mapping. maskflow/__init__.py used to import
pack-india first, so pack-intl silently replaced pack-india's Indian context
keywords ("नाम", "श्री", ...) and its spaCy agreement boost and span filter.
"""

import maskflow
from maskflow_core.context import CONTEXT_KEYWORDS
from maskflow_core.entities import PIIType
from maskflow_core.registry import NER_RECOGNIZERS
from maskflow_pack_india import _plausible_person_entity


def test_pack_india_owns_the_spacy_person_mapping() -> None:
    mapping = NER_RECOGNIZERS["PERSON"]
    assert mapping.span_filter is _plausible_person_entity
    assert mapping.agreement_boost > 0


def test_person_name_context_keywords_include_both_packs() -> None:
    keywords = CONTEXT_KEYWORDS[PIIType.register("PERSON_NAME")]
    assert "नाम" in keywords  # pack-india
    assert "my name" in keywords  # pack-intl


def test_readme_quickstart_example() -> None:
    # Kept identical to README.md's Quickstart. Synthetic Aadhaar number:
    # passes the Verhoeff checksum, belongs to no one.
    text = "My Aadhaar is 2346 8907 6549 and you can reach me at alice@example.com."
    result = maskflow.mask(text)
    assert result.masked_text == "My Aadhaar is <AADHAAR_1> and you can reach me at <EMAIL_1>."
    assert maskflow.unmask(result.masked_text, result.mapping) == text


def test_readme_quickstart_matches_the_readme() -> None:
    from pathlib import Path

    readme = (Path(__file__).resolve().parents[3] / "README.md").read_text(encoding="utf-8")
    assert (
        'mask("My Aadhaar is 2346 8907 6549 and you can reach me at alice@example.com.")' in readme
    )
    assert '"My Aadhaar is <AADHAAR_1> and you can reach me at <EMAIL_1>."' in readme
