"""Guards against PII reaching logs, exceptions, repr, or test output (rule #1)."""

import pytest
from maskflow_core.entities import PIIType, Span


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
