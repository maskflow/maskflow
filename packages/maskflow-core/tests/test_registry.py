import re

import pytest
from maskflow_core import mask, register_pattern, unmask
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def test_registered_pii_type_behaves_as_a_plain_string() -> None:
    """Core registers zero built-in types -- this proves the open-registry
    mechanism itself (str subclass, .value, singleton-per-name) rather than
    any particular pack's type, which is pack content, not engine behavior."""
    registered = PIIType.register("BADGE_ID")
    assert registered == "BADGE_ID"
    assert registered.value == "BADGE_ID"
    assert isinstance(registered, str)


def test_register_is_idempotent_and_returns_the_same_singleton() -> None:
    first = PIIType.register("WIDGET_ID")
    second = PIIType.register("WIDGET_ID")
    assert first is second
    # setattr()-installed at registration time -- mypy can't know statically
    # that this attribute exists.
    assert PIIType.WIDGET_ID is first  # type: ignore[attr-defined]


def test_register_rejects_non_upper_snake_names() -> None:
    with pytest.raises(ValueError):
        PIIType.register("not-upper-snake")
    with pytest.raises(ValueError):
        PIIType.register("lowercase")


def test_unregistered_type_construction_raises() -> None:
    with pytest.raises(ValueError):
        PIIType("TOTALLY_UNKNOWN_TYPE")


def test_register_pattern_extends_detection_without_touching_patterns_module() -> None:
    """Proves a future pack (e.g. maskflow-pack-india) can add a recognizer
    purely through the public API, and it flows through detect()/mask()/unmask()
    exactly like any other registered type."""
    widget_re = re.compile(r"\bWID-\d{6}\b")
    widget_type = register_pattern("WIDGET_ID", widget_re, 0.9)

    assert widget_type == "WIDGET_ID"

    text = "Please reference widget WID-123456 in your reply."
    spans = detect(text)
    assert any(s.entity_type == "WIDGET_ID" and s.text == "WID-123456" for s in spans)

    result = mask(text)
    assert "WID-123456" not in result.masked_text
    assert "<WIDGET_ID_1>" in result.masked_text
    assert unmask(result.masked_text, result.mapping) == text

    # A second, unrelated registration is unaffected by the first.
    gadget_re = re.compile(r"\bGAD-\d{4}\b")
    register_pattern("GADGET_ID", gadget_re, 0.9)
    existing = detect("Contact us about gadget GAD-1234 for details.")
    assert any(s.entity_type == "GADGET_ID" and s.text == "GAD-1234" for s in existing)
