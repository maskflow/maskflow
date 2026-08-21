"""Tests for maskflow.session(): value->token identity stable across calls
(the bug plain mask() has -- see session.py's module docstring), mask_json's
type/key preservation, close()/TTL purging the mapping, and round trips.
"""

import time
from typing import Any

import pytest
from maskflow import SessionClosedError, session


def test_same_value_gets_same_token_across_separate_calls() -> None:
    with session() as s:
        first = s.mask("Call me at 415-555-0132.")
        second = s.mask("Reminder: 415-555-0132 again.")

    assert "<PHONE_1>" in first
    assert "<PHONE_1>" in second
    assert "415-555-0132" not in first
    assert "415-555-0132" not in second


def test_different_values_get_distinct_tokens_across_calls() -> None:
    """The bug this feature fixes: two independent mask() calls would each
    restart counters at 1, so two *different* phone numbers could both be
    "<PHONE_1>" -- session() must not let that happen."""
    with session() as s:
        first = s.mask("Contact: 415-555-0132.")
        second = s.mask("Also try 415-555-0199.")

    assert "<PHONE_1>" in first
    assert "<PHONE_2>" in second
    assert "<PHONE_1>" not in second


def test_mask_round_trips_through_unmask() -> None:
    text = "Email me at alice@example.com or call 415-555-0132."
    with session() as s:
        masked = s.mask(text)
        restored = s.unmask(masked)
    assert restored == text


def test_mask_json_only_masks_string_leaves_never_keys() -> None:
    with session() as s:
        result = s.mask_json({"email": "alice@example.com", "note": "no pii here"})

    assert "email" in result  # key untouched
    assert result["email"] != "alice@example.com"
    assert result["email"].startswith("<EMAIL_")
    assert result["note"] == "no pii here"


def test_mask_json_preserves_container_and_scalar_types() -> None:
    with session() as s:
        result = s.mask_json(
            {
                "contacts": ["alice@example.com", "bob@example.com"],
                "active": True,
                "count": 3,
                "ratio": 0.5,
                "nested": {"deep": {"email": "carol@example.com"}},
            }
        )

    assert isinstance(result["contacts"], list)
    assert result["active"] is True
    assert result["count"] == 3
    assert result["ratio"] == 0.5
    assert result["nested"]["deep"]["email"].startswith("<EMAIL_")


# A well-known Luhn-valid test card number, universally reserved for testing
# and never issued to a real cardholder -- synthetic per CLAUDE.md rule 2.
_SYNTHETIC_CARD_NUMBER = 4111111111111111


def test_mask_json_numeric_pii_leaf_stays_an_int() -> None:
    with session() as s:
        result = s.mask_json({"card": _SYNTHETIC_CARD_NUMBER})

    assert isinstance(result["card"], int)
    assert result["card"] != _SYNTHETIC_CARD_NUMBER
    assert len(str(result["card"])) == len(str(_SYNTHETIC_CARD_NUMBER))


def test_mask_json_non_pii_numbers_bools_and_none_pass_through() -> None:
    with session() as s:
        result = s.mask_json({"count": 7, "active": False, "missing": None, "ratio": 1.25})

    assert result == {"count": 7, "active": False, "missing": None, "ratio": 1.25}


def test_mask_json_numeric_leaf_round_trips_via_unmask_on_dumped_text() -> None:
    import json

    with session() as s:
        masked = s.mask_json({"card": _SYNTHETIC_CARD_NUMBER})
        restored_text = s.unmask(json.dumps(masked))

    assert json.loads(restored_text) == {"card": _SYNTHETIC_CARD_NUMBER}


def test_mask_json_same_value_reuses_token_across_calls() -> None:
    with session() as s:
        first = s.mask_json({"email": "alice@example.com"})
        second = s.mask_json({"contact": "alice@example.com"})

    assert first["email"] == second["contact"]


def test_mask_json_rejects_excessive_depth() -> None:
    node: Any = "leaf"
    for _ in range(50):
        node = [node]

    with session() as s, pytest.raises(ValueError, match="max_depth"):
        s.mask_json(node, max_depth=10)


def test_mask_json_rejects_excessive_item_count() -> None:
    wide = list(range(50))

    with session() as s, pytest.raises(ValueError, match="max_items"):
        s.mask_json(wide, max_items=10)


def test_close_purges_the_mapping_and_blocks_further_use() -> None:
    s = session()
    s.mask("Email me at alice@example.com.")
    assert len(s._mapping) > 0

    s.close()

    assert len(s._mapping) == 0
    assert len(s._value_tokens) == 0
    assert len(s._reserved) == 0
    with pytest.raises(SessionClosedError):
        s.mask("Email me at bob@example.com.")
    with pytest.raises(SessionClosedError):
        s.unmask("<EMAIL_1>")
    with pytest.raises(SessionClosedError):
        s.mask_json({"email": "carol@example.com"})


def test_context_manager_closes_on_exit() -> None:
    with session() as s:
        s.mask("Email me at alice@example.com.")
        assert len(s._mapping) > 0
    assert len(s._mapping) == 0


def test_ttl_expiry_purges_the_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    s = session(ttl_seconds=10)
    s.mask("Email me at alice@example.com.")
    assert len(s._mapping) > 0

    clock["now"] = 10.0
    with pytest.raises(SessionClosedError):
        s.mask("Email me at bob@example.com.")
    assert len(s._mapping) == 0


def test_ttl_none_disables_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    s = session(ttl_seconds=None)
    s.mask("Email me at alice@example.com.")
    clock["now"] = 10**9
    s.mask("Email me at bob@example.com.")  # must not raise
    s.close()
