"""spacy-based detection for entity types regex can't reliably catch: names and dates."""
from functools import lru_cache

import spacy

from .context import apply_context_boost
from .entities import Finding, PIIType

MODEL_NAME = "en_core_web_sm"

PERSON_BASE_CONFIDENCE = 0.75
DATE_BASE_CONFIDENCE = 0.3
DATE_OF_BIRTH_THRESHOLD = 0.6


@lru_cache(maxsize=1)
def _get_nlp():
    return spacy.load(MODEL_NAME)


def detect_ner(text: str) -> list[Finding]:
    nlp = _get_nlp()
    doc = nlp(text)
    findings: list[Finding] = []

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            confidence = apply_context_boost(
                text, ent.start_char, ent.end_char, PIIType.PERSON_NAME, PERSON_BASE_CONFIDENCE
            )
            findings.append(
                Finding(PIIType.PERSON_NAME, ent.text, ent.start_char, ent.end_char, confidence)
            )
        elif ent.label_ == "DATE":
            confidence = apply_context_boost(
                text, ent.start_char, ent.end_char, PIIType.DATE_OF_BIRTH, DATE_BASE_CONFIDENCE
            )
            if confidence >= DATE_OF_BIRTH_THRESHOLD:
                findings.append(
                    Finding(PIIType.DATE_OF_BIRTH, ent.text, ent.start_char, ent.end_char, confidence)
                )

    return findings
