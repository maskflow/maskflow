"""snapshot()/restore() round trip: a session's masking state survives
serialization to bytes and back, and a restored session keeps minting
tokens exactly where the original left off (the property maskflow-gateway
needs to move a session's mapping through Redis between processes).
"""

import json

import pytest
from maskflow import SessionClosedError, session
from maskflow.session import _SNAPSHOT_VERSION


def test_snapshot_restore_preserves_mapping_and_round_trip() -> None:
    text = "Email alice@example.com or call 415-555-0132."
    with session() as original:
        masked = original.mask(text)
        blob = original.snapshot()

    with session() as restored:
        restored.restore(blob)
        assert restored.unmask(masked) == text


def test_restored_session_continues_token_numbering() -> None:
    with session() as original:
        first = original.mask("Contact: 415-555-0132.")
        blob = original.snapshot()

    with session() as restored:
        restored.restore(blob)
        # Same value -> same token as before the snapshot.
        again = restored.mask("Reminder: 415-555-0132.")
        # A genuinely new value -> the *next* counter, not a reset to 1.
        other = restored.mask("Also try 415-555-0199.")

    assert "<PHONE_1>" in first
    assert "<PHONE_1>" in again
    assert "<PHONE_2>" in other


def test_snapshot_is_utf8_json_with_a_version() -> None:
    with session() as s:
        s.mask("Email alice@example.com.")
        payload = json.loads(s.snapshot().decode("utf-8"))
    assert payload["v"] == _SNAPSHOT_VERSION


def test_restore_rejects_unknown_version() -> None:
    with session() as s:
        with pytest.raises(ValueError, match="snapshot version"):
            s.restore(json.dumps({"v": 999}).encode("utf-8"))


def test_snapshot_on_closed_session_raises() -> None:
    s = session()
    s.close()
    with pytest.raises(SessionClosedError):
        s.snapshot()


def test_numeric_leaf_surrogate_survives_snapshot() -> None:
    card = 4111111111111111
    with session() as original:
        masked = original.mask_json({"card": card})
        blob = original.snapshot()

    with session() as restored:
        restored.restore(blob)
        restored_text = restored.unmask(json.dumps(masked))
    assert json.loads(restored_text) == {"card": card}


def test_patterns_only_routes_through_detect_patterns_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flag's contract: the NER-inclusive detect() is never called."""
    import sys

    session_mod = sys.modules["maskflow.session"]

    def _boom(*_args: object, **_kwargs: object) -> list[object]:
        raise AssertionError("detect() (NER pass) must not run when patterns_only=True")

    monkeypatch.setattr(session_mod, "detect", _boom)
    with session(patterns_only=True) as s:
        out = s.mask("PAN AAAPZ1234C, mail alice@example.com")
    assert "AAAPZ1234C" not in out
    assert "alice@example.com" not in out


def test_patterns_only_flag_survives_snapshot() -> None:
    with session(patterns_only=True) as original:
        original.mask("mail alice@example.com")
        blob = original.snapshot()
    with session() as restored:
        restored.restore(blob)
        assert restored._patterns_only is True
