"""mask_with_policy()'s 5-strategy matrix -- replace/surrogate round-trip via
unmask(); redact/mask/hash produce the expected substitute text and a
non-reversible MappingEntry, and unmask() leaves their substitute text
untouched (documented, tested behavior -- not a silent no-op). See
strategies.py's module docstring for why redact/mask/hash aren't reversible.
"""

import re

import pytest
from maskflow_core.mapping import MappingEntry
from maskflow_core.masking import mask_with_policy, unmask
from maskflow_core.policy import MaskPolicy
from maskflow_core.registry import register_pattern, register_surrogate_generator
from maskflow_core.strategies import HashConfig, MaskConfig, Strategy

# A distinct fixture pattern/value from test_registry.py's WIDGET_ID example
# is deliberate -- this module registers TEST_WIDGET at import time (which
# runs once, for the whole pytest session, regardless of test selection), so
# reusing the same regex/example text there would make the two types
# structurally identical and shadow each other during overlap resolution.
GADGET_RE = re.compile(r"\bGADGET-\d{6}\b")
register_pattern("TEST_WIDGET", GADGET_RE, 0.95)


def test_replace_strategy_matches_default_mask_behavior() -> None:
    text = "Ref GADGET-123456 please."
    result = mask_with_policy(text, MaskPolicy(default_strategy=Strategy.REPLACE))

    assert result.masked_text == "Ref <TEST_WIDGET_1> please."
    entry = result.mapping["<TEST_WIDGET_1>"]
    assert isinstance(entry, MappingEntry)
    assert entry.reversible is True
    assert entry.strategy is Strategy.REPLACE
    assert unmask(result.masked_text, result.mapping) == text


def test_redact_strategy_produces_type_tagged_marker_and_is_not_reversible() -> None:
    text = "Ref GADGET-123456 please."
    result = mask_with_policy(text, MaskPolicy(default_strategy=Strategy.REDACT))

    assert result.masked_text == "Ref [REDACTED_TEST_WIDGET] please."
    entries = list(result.mapping.values())
    assert len(entries) == 1
    assert entries[0].reversible is False
    assert entries[0].original == "GADGET-123456"
    # unmask() must leave redacted text untouched -- there's nothing to
    # restore it to unambiguously (see module docstring).
    assert unmask(result.masked_text, result.mapping) == result.masked_text


def test_redact_strategy_collapses_distinct_values_but_keeps_both_audit_entries() -> None:
    text = "GADGET-123456 and GADGET-654321 both redacted."
    result = mask_with_policy(text, MaskPolicy(default_strategy=Strategy.REDACT))

    assert result.masked_text.count("[REDACTED_TEST_WIDGET]") == 2
    originals = {entry.original for entry in result.mapping.values()}
    assert originals == {"GADGET-123456", "GADGET-654321"}


def test_mask_strategy_reveals_only_the_configured_tail() -> None:
    text = "Ref GADGET-123456 please."
    policy = MaskPolicy(
        default_strategy=Strategy.MASK, mask_config=MaskConfig(reveal_last=4, mask_char="X")
    )
    result = mask_with_policy(text, policy)

    assert result.masked_text == "Ref XXXXXX-XX3456 please."
    entry = next(iter(result.mapping.values()))
    assert entry.reversible is False
    assert unmask(result.masked_text, result.mapping) == result.masked_text


def test_hash_strategy_is_stable_for_the_same_value() -> None:
    text = "GADGET-123456 appears twice: GADGET-123456."
    policy = MaskPolicy(default_strategy=Strategy.HASH, hash_config=HashConfig(key=b"\x00" * 32))
    result = mask_with_policy(text, policy)

    tokens_in_text = re.findall(r"\b[0-9a-f]{64}\b", result.masked_text)
    assert len(tokens_in_text) == 2
    assert tokens_in_text[0] == tokens_in_text[1]  # same value -> same digest
    assert all(not entry.reversible for entry in result.mapping.values())


def test_hash_strategy_differs_by_key() -> None:
    text = "Ref GADGET-123456 please."
    result_a = mask_with_policy(
        text, MaskPolicy(default_strategy=Strategy.HASH, hash_config=HashConfig(key=b"\x00" * 32))
    )
    result_b = mask_with_policy(
        text, MaskPolicy(default_strategy=Strategy.HASH, hash_config=HashConfig(key=b"\x01" * 32))
    )
    assert result_a.masked_text != result_b.masked_text


def test_hash_strategy_without_a_key_raises_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASKFLOW_HASH_KEY", raising=False)
    text = "Ref GADGET-123456 please."
    try:
        mask_with_policy(text, MaskPolicy(default_strategy=Strategy.HASH))
    except ValueError as exc:
        assert "MASKFLOW_HASH_KEY" in str(exc)
    else:
        raise AssertionError("expected ValueError for a missing hash key")


def test_surrogate_strategy_round_trips_via_unmask() -> None:
    register_surrogate_generator(
        "TEST_WIDGET",
        lambda _v, rng: f"GADGET-{rng.randint(0, 999999):06d}",
        "test range",
    )
    text = "Ref GADGET-123456 please."
    result = mask_with_policy(text, MaskPolicy(default_strategy=Strategy.SURROGATE))

    assert "GADGET-123456" not in result.masked_text
    entry = next(iter(result.mapping.values()))
    assert entry.reversible is True
    assert unmask(result.masked_text, result.mapping) == text


def test_surrogate_strategy_falls_back_to_replace_with_no_registered_generator() -> None:
    text = "Ref GADGET-123456 please."
    result = mask_with_policy(text, MaskPolicy(default_strategy=Strategy.SURROGATE))

    assert result.masked_text == "Ref <TEST_WIDGET_1> please."
    entry = result.mapping["<TEST_WIDGET_1>"]
    assert entry.reversible is True
    assert unmask(result.masked_text, result.mapping) == text


def test_replace_strategy_avoids_colliding_with_placeholder_lookalike_text() -> None:
    text = "Keep <TEST_WIDGET_1> literally. Ref GADGET-123456."
    result = mask_with_policy(text, MaskPolicy(default_strategy=Strategy.REPLACE))

    assert "<TEST_WIDGET_1>" not in result.mapping
    assert unmask(result.masked_text, result.mapping) == text


def test_surrogate_strategy_falls_back_to_replace_when_generator_keeps_colliding() -> None:
    # A generator that always returns the same value can never be unique
    # once one instance has claimed it -- mask_with_policy() must give up
    # after a bounded number of retries and fall back to a REPLACE token
    # rather than looping forever or emitting a duplicate.
    register_surrogate_generator("TEST_WIDGET", lambda _v, _rng: "GADGET-000000", "always collides")
    text = "GADGET-123456 and GADGET-654321 both need a surrogate."
    result = mask_with_policy(text, MaskPolicy(default_strategy=Strategy.SURROGATE))

    assert result.masked_text.count("GADGET-000000") == 1
    assert "<TEST_WIDGET_" in result.masked_text
    assert unmask(result.masked_text, result.mapping) == text


def test_per_entity_strategy_override_mixes_strategies_in_one_call() -> None:
    # A synthetic, non-real-world-shaped second pattern is deliberate (like
    # GADGET_RE above) -- a realistic shape (e.g. an email address) risks
    # losing entity-type resolution to a same-shaped real recognizer from
    # another installed pack, if one ever happens to be loaded in the same
    # process (packs are tested in separate CI processes, but nothing stops
    # a local combined run).
    gizmo_re = re.compile(r"\bGIZMO-\d{6}\b")
    test_gizmo_type = register_pattern("TEST_GIZMO", gizmo_re, 0.95)
    text = "Contact GADGET-123456 or GIZMO-654321."

    policy = MaskPolicy(
        default_strategy=Strategy.REPLACE,
        per_entity_strategy={test_gizmo_type: Strategy.REDACT},
    )
    result = mask_with_policy(text, policy)

    assert "<TEST_WIDGET_1>" in result.masked_text
    assert "[REDACTED_TEST_GIZMO]" in result.masked_text
    restored = unmask(result.masked_text, result.mapping)
    assert "GADGET-123456" in restored
    assert "[REDACTED_TEST_GIZMO]" in restored  # redaction itself never reverses
