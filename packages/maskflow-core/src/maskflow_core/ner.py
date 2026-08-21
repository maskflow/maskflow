"""Generic spaCy-based NER pass.

Loads the model once (spaCy itself is optional -- install maskflow-core[nlp]
to enable this pass) and turns doc.ents whose label has been registered via
registry.register_ner_recognizer() into Findings. Core has no opinion about
which entity types matter; that mapping is entirely pack content.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Any

from .context import apply_context_boost
from .entities import PIIType, Span
from .registry import NER_RECOGNIZERS

MODEL_NAME = "en_core_web_sm"


@lru_cache(maxsize=1)
def _get_nlp() -> Any:
    # lru_cache(maxsize=1) means this body runs at most once per process, so
    # the warning below naturally fires at most once too -- no separate
    # "have I warned yet" flag needed.
    try:
        import spacy
    except ImportError:
        warnings.warn(
            "spaCy isn't installed (install maskflow-core[nlp] to enable it) -- "
            "NER-based recognizers are disabled for this process. Pattern-based "
            "recognizers are unaffected.",
            stacklevel=2,
        )
        return None

    try:
        return spacy.load(MODEL_NAME)
    except OSError as exc:
        raise OSError(
            f"spaCy model '{MODEL_NAME}' isn't installed. Run: "
            f"python -m spacy download {MODEL_NAME}"
        ) from exc


def detect_ner(text: str, disabled_types: frozenset[PIIType] = frozenset()) -> list[Span]:
    if not NER_RECOGNIZERS:
        # Nothing registered a spaCy label -- skip loading the model entirely,
        # so a core-only install with no [nlp]/pack never even tries to import
        # spaCy, let alone warn about it being missing.
        return []

    nlp = _get_nlp()
    if nlp is None:
        return []

    doc = nlp(text)
    spans: list[Span] = []

    for ent in doc.ents:
        mapping = NER_RECOGNIZERS.get(ent.label_)
        if mapping is None:
            continue
        if mapping.pii_type in disabled_types:
            continue

        confidence = apply_context_boost(
            text, ent.start_char, ent.end_char, mapping.pii_type, mapping.base_confidence
        )
        if confidence >= mapping.threshold:
            spans.append(
                Span(
                    start=ent.start_char,
                    end=ent.end_char,
                    entity_type=mapping.pii_type,
                    score=confidence,
                    recognizer=f"ner:{ent.label_}",
                    text=ent.text,
                )
            )

    return spans
