"""spaCy entity-label mappings for the intl PERSON/DATE recognizers.

Confidence values and DATE_OF_BIRTH_THRESHOLD are unchanged from the original
maskflow-core NER pass -- only the label -> PIIType wiring moved here, since
core no longer hardcodes PERSON/DATE handling. __init__.py feeds these into
maskflow_core.registry.register_ner_recognizer().
"""

PERSON_BASE_CONFIDENCE = 0.75
DATE_BASE_CONFIDENCE = 0.3
DATE_OF_BIRTH_THRESHOLD = 0.6
