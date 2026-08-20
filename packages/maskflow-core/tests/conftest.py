"""Isolates each test from registry state mutated by other tests.

register_pattern()/register_ner_recognizer() write into module-level globals
(PATTERNS, NER_RECOGNIZERS, CONTEXT_KEYWORDS) that would otherwise leak
across test files within the same pytest session -- e.g. test_ner.py
registering a spaCy label would make an unrelated test_registry.py test's
detect() call unexpectedly try to load the real spaCy model.
"""

from collections.abc import Iterator

import pytest
from maskflow_core.context import CONTEXT_KEYWORDS
from maskflow_core.registry import NER_RECOGNIZERS, PATTERNS, SURROGATE_GENERATORS
from maskflow_core.testing import (  # noqa: F401 -- picked up as pytest hooks by name
    pytest_collection_modifyitems,
    pytest_configure,
    pytest_exception_interact,
)


@pytest.fixture(autouse=True)
def _reset_registry_state() -> Iterator[None]:
    patterns_snapshot = {k: list(v) for k, v in PATTERNS.items()}
    ner_snapshot = dict(NER_RECOGNIZERS)
    keywords_snapshot = dict(CONTEXT_KEYWORDS)
    surrogates_snapshot = dict(SURROGATE_GENERATORS)

    yield

    PATTERNS.clear()
    PATTERNS.update(patterns_snapshot)
    NER_RECOGNIZERS.clear()
    NER_RECOGNIZERS.update(ner_snapshot)
    CONTEXT_KEYWORDS.clear()
    CONTEXT_KEYWORDS.update(keywords_snapshot)
    SURROGATE_GENERATORS.clear()
    SURROGATE_GENERATORS.update(surrogates_snapshot)
