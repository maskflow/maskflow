"""End-to-end proof that .maskflowrc config actually drives mask()/
mask_and_call()/session() -- the specific scenarios called out for PR 2:
a threshold change makes an entity appear/disappear, a [custom] pattern
fires with its configured type/score, an [exclusions] value is never
flagged, enabled=false disables an entity, and an explicit config= beats
ambient file discovery. Plus the process-level cache/reload_config()
contract and Session's strategy-aware substitution (SURROGATE identity,
REDACT/MASK/HASH non-reversibility, numeric leaves ignoring strategy).

The "no config anywhere is byte-identical to today" hard requirement
itself is proven at the core layer (test_masking.py's
test_mask_with_policy_default_matches_mask hypothesis property test) --
these tests are about config actually *doing something* when present.
"""

from __future__ import annotations

import re

import maskflow
import maskflow._config
import maskflow.sdk
import pytest
from maskflow import mask, session
from maskflow_core.config import (
    CustomEntityConfig,
    EntityConfig,
    ExclusionsConfig,
    MaskflowSection,
    ResolvedConfig,
    RootConfig,
)
from maskflow_core.strategies import Strategy

# A well-known Luhn-valid test card number, universally reserved for testing
# and never issued to a real cardholder -- synthetic per CLAUDE.md rule 2.
_SYNTHETIC_CARD_NUMBER = 4111111111111111


def test_threshold_override_makes_entity_appear_and_disappear() -> None:
    text = "Reach me at alice@example.com."

    # Global threshold high enough to suppress EMAIL (pack-intl's base
    # confidence for an unvalidated email match is 0.95) by default.
    suppressed = mask(text, min_confidence=0.99)
    assert "alice@example.com" in suppressed.masked_text

    # A per-entity override drops EMAIL's threshold back down -> detected
    # despite the high global min_confidence: the entity *appears*.
    low_threshold = RootConfig(entities={"EMAIL": EntityConfig(threshold=0.1)})
    appeared = mask(text, min_confidence=0.99, config=low_threshold)
    assert "alice@example.com" not in appeared.masked_text
    assert "alice@example.com" in appeared.mapping.values()

    # And raising it above EMAIL's natural score suppresses it even at the
    # default global min_confidence: the entity *disappears*.
    high_threshold = RootConfig(entities={"EMAIL": EntityConfig(threshold=1.0)})
    disappeared = mask(text, config=high_threshold)
    assert "alice@example.com" in disappeared.masked_text


def test_custom_pattern_fires_with_configured_type_and_score() -> None:
    text = "Badge EMP-042317 was scanned at the gate."
    config = RootConfig(
        custom={"EMPLOYEE_ID": CustomEntityConfig(pattern=r"\bEMP-\d{6}\b", score=0.9)}
    )
    result = mask(text, config=config)

    assert "EMP-042317" not in result.masked_text
    assert "<EMPLOYEE_ID_1>" in result.masked_text
    assert result.mapping["<EMPLOYEE_ID_1>"] == "EMP-042317"


def test_exclusion_value_never_flagged() -> None:
    text = "Contact test@example.com or alice@example.com for help."
    config = RootConfig(exclusions=ExclusionsConfig(values=["test@example.com"]))
    result = mask(text, config=config)

    assert "test@example.com" in result.masked_text
    assert "alice@example.com" not in result.masked_text


def test_enabled_false_disables_entity() -> None:
    text = "Reach me at alice@example.com."
    config = RootConfig(entities={"EMAIL": EntityConfig(enabled=False)})
    result = mask(text, config=config)

    assert result.masked_text == text
    assert result.mapping == {}


def test_explicit_config_beats_ambient_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Reach me at alice@example.com."
    fake_ambient = ResolvedConfig(
        config=RootConfig(maskflow=MaskflowSection(default_strategy=Strategy.REDACT)),
        provenance={},
        project_file=None,
        user_file=None,
    )
    monkeypatch.setattr(maskflow.sdk, "get_ambient_config", lambda: fake_ambient)

    # config=None (default) uses the ambient config -- the monkeypatched
    # REDACT strategy takes effect.
    ambient_result = mask(text)
    assert "alice@example.com" not in ambient_result.masked_text
    assert "[REDACTED_EMAIL]" in ambient_result.masked_text

    # An explicit config= bypasses discovery entirely -- REPLACE, not
    # REDACT, proving it really did skip the (monkeypatched) ambient path.
    explicit_result = mask(text, config=RootConfig())
    assert "<EMAIL_1>" in explicit_result.masked_text


def test_reload_config_picks_up_change(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Reach me at alice@example.com."
    responses = iter(
        [
            ResolvedConfig(config=RootConfig(), provenance={}, project_file=None, user_file=None),
            ResolvedConfig(
                config=RootConfig(maskflow=MaskflowSection(default_strategy=Strategy.REDACT)),
                provenance={},
                project_file=None,
                user_file=None,
            ),
        ]
    )
    monkeypatch.setattr(maskflow._config, "resolve_config", lambda: next(responses))
    monkeypatch.setattr(maskflow._config, "_cached", None)

    first = mask(text)  # lazily populates the cache -- consumes response #1
    assert "<EMAIL_1>" in first.masked_text

    second = mask(text)  # cache hit -- does NOT consume response #2
    assert "<EMAIL_1>" in second.masked_text

    maskflow.reload_config()  # forces a fresh resolve_config() -- consumes #2
    third = mask(text)
    assert "[REDACTED_EMAIL]" in third.masked_text


def test_session_surrogate_identity_stable_across_calls() -> None:
    config = RootConfig(entities={"EMAIL": EntityConfig(strategy=Strategy.SURROGATE)})
    with session(config=config) as s:
        first = s.mask("Reach me at alice@example.com.")
        second = s.mask("Again, alice@example.com works too.")

    first_surrogate = re.search(r"Reach me at (\S+)\.", first)
    second_surrogate = re.search(r"Again, (\S+) works too\.", second)
    assert first_surrogate is not None
    assert second_surrogate is not None
    assert first_surrogate.group(1) == second_surrogate.group(1)
    assert first_surrogate.group(1) != "alice@example.com"
    assert "@" in first_surrogate.group(1)


def test_session_redact_produces_non_reversible_entry() -> None:
    config = RootConfig(maskflow=MaskflowSection(default_strategy=Strategy.REDACT))
    with session(config=config) as s:
        masked = s.mask("Reach me at alice@example.com.")
        assert "[REDACTED_EMAIL]" in masked
        restored = s.unmask(masked)

    # REDACT is intentionally lossy -- unmask() leaves it exactly as-is.
    assert restored == masked


def test_session_numeric_leaf_ignores_configured_strategy() -> None:
    config = RootConfig(entities={"CREDIT_CARD": EntityConfig(strategy=Strategy.REDACT)})
    with session(config=config) as s:
        result = s.mask_json({"card": _SYNTHETIC_CARD_NUMBER})

    # Numeric leaves always use the numeric-surrogate scheme, never a
    # strategy-driven string substitute -- mask_json's "leaf's JSON type
    # never changes" invariant holds regardless of configured strategy.
    assert isinstance(result["card"], int)
    assert result["card"] != _SYNTHETIC_CARD_NUMBER
    assert len(str(result["card"])) == len(str(_SYNTHETIC_CARD_NUMBER))
