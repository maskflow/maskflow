"""Guards against PII reaching logs, exceptions, repr, or test output (rule #1).

This file covers the "repr" leg directly, per-class. See
maskflow_core.testing / test_leak_gate.py for the "log record"/"exception"
legs, captured across the whole test session.
"""

import pytest
from maskflow_core.entities import PIIType, Span
from maskflow_core.mapping import Mapping, MappingEntry
from maskflow_core.strategies import Strategy


@pytest.mark.leak
def test_span_repr_excludes_raw_text() -> None:
    secret_type = PIIType.register("SECRET_ID")
    span = Span(
        start=0,
        end=11,
        entity_type=secret_type,
        score=0.95,
        recognizer="pattern:SECRET_ID",
        text="245-11-2222",
    )
    assert "245-11-2222" not in repr(span)
    assert "SECRET_ID" in repr(span)


@pytest.mark.leak
def test_mapping_entry_repr_excludes_original() -> None:
    secret_type = PIIType.register("SECRET_ID")
    entry = MappingEntry(
        token="<SECRET_ID_1>",
        entity_type=secret_type,
        strategy=Strategy.REPLACE,
        reversible=True,
        original="245-11-2222",
    )
    assert "245-11-2222" not in repr(entry)
    assert "<SECRET_ID_1>" in repr(entry)


@pytest.mark.leak
def test_mapping_repr_excludes_original_values() -> None:
    secret_type = PIIType.register("SECRET_ID")
    entry = MappingEntry(
        token="<SECRET_ID_1>",
        entity_type=secret_type,
        strategy=Strategy.REPLACE,
        reversible=True,
        original="245-11-2222",
    )
    mapping = Mapping({"<SECRET_ID_1>": entry})
    assert "245-11-2222" not in repr(mapping)
    assert "<SECRET_ID_1>" in repr(mapping)
