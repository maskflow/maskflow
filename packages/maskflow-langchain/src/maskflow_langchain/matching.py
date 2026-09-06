"""Deanonymizer mapping type and matching strategies.

``MappingDataType`` and ``exact_matching_strategy`` mirror
``langchain_experimental.data_anonymizer`` exactly, so a chain that passes a
custom strategy to ``.deanonymize(...)`` keeps working after the import
swap. MaskFlow placeholders (``<PAN_1>``) are exact by construction, so
``exact_matching_strategy`` is the default and is all most chains need;
``case_insensitive_matching_strategy`` is provided for parity.
"""

from __future__ import annotations

import re

# {entity_type: {anonymized_value: original_value}}
MappingDataType = dict[str, dict[str, str]]


def exact_matching_strategy(text: str, deanonymizer_mapping: MappingDataType) -> str:
    """Replace every anonymized value in ``text`` with its original, longest
    match first so a value that is a substring of another is not clobbered."""
    for entity_type in deanonymizer_mapping:
        for anonymized, original in sorted(
            deanonymizer_mapping[entity_type].items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            text = text.replace(anonymized, original)
    return text


def case_insensitive_matching_strategy(text: str, deanonymizer_mapping: MappingDataType) -> str:
    """Like ``exact_matching_strategy`` but case-insensitive on the anonymized
    value. MaskFlow tokens are uppercase, so this only matters if a model
    lower-cased one."""
    for entity_type in deanonymizer_mapping:
        for anonymized, original in sorted(
            deanonymizer_mapping[entity_type].items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            text = re.sub(re.escape(anonymized), original, text, flags=re.IGNORECASE)
    return text


DEFAULT_DEANONYMIZER_MATCHING_STRATEGY = exact_matching_strategy
