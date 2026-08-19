import re

import pytest

from maskflow_core import mask, register_pattern, unmask
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def test_builtin_pii_types_still_work_as_before():
    assert PIIType.EMAIL == "EMAIL"
    assert PIIType.EMAIL.value == "EMAIL"
    assert isinstance(PIIType.EMAIL, str)


def test_register_is_idempotent_and_returns_the_same_singleton():
    first = PIIType.register("WIDGET_ID")
    second = PIIType.register("WIDGET_ID")
    assert first is second
    assert PIIType.WIDGET_ID is first


def test_register_rejects_non_upper_snake_names():
    with pytest.raises(ValueError):
        PIIType.register("not-upper-snake")
    with pytest.raises(ValueError):
        PIIType.register("lowercase")


def test_unregistered_type_construction_raises():
    with pytest.raises(ValueError):
        PIIType("TOTALLY_UNKNOWN_TYPE")


def test_register_pattern_extends_detection_without_touching_patterns_module():
    """Proves a future pack (e.g. maskflow-pack-india) can add a recognizer
    purely through the public API, and it flows through detect()/mask()/unmask()
    exactly like a built-in type."""
    widget_re = re.compile(r"\bWID-\d{6}\b")
    widget_type = register_pattern("WIDGET_ID", widget_re, 0.9)

    assert widget_type == "WIDGET_ID"

    text = "Please reference widget WID-123456 in your reply."
    findings = detect(text)
    assert any(f.type == "WIDGET_ID" and f.value == "WID-123456" for f in findings)

    result = mask(text)
    assert "WID-123456" not in result.masked_text
    assert "<WIDGET_ID_1>" in result.masked_text
    assert unmask(result.masked_text, result.mapping) == text

    # Existing built-in detection is unaffected by the new registration.
    existing = detect("Contact carol@example.com for details.")
    assert any(f.type == PIIType.EMAIL and f.value == "carol@example.com" for f in existing)
