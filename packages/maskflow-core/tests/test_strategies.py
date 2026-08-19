"""Strategy-level unit coverage for pieces mask_with_policy() drives but
doesn't exercise every branch of on its own: HashConfig's env-var key
resolution, MaskConfig's reveal_last=0 edge case, and apply_strategy()'s
defensive guard against being called for REPLACE/SURROGATE (which
masking.py always resolves itself -- see strategies.py's module docstring).
"""

import pytest
from maskflow_core.entities import PIIType, Span
from maskflow_core.strategies import HashConfig, MaskConfig, Strategy, apply_strategy


def _span(text: str = "245-11-2222") -> Span:
    pii_type = PIIType.register("TEST_STRATEGY_TYPE")
    return Span(
        start=0, end=len(text), entity_type=pii_type, score=0.9, recognizer="test", text=text
    )


def test_hash_config_resolves_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASKFLOW_HASH_KEY", "ab" * 32)
    assert HashConfig().resolved_key() == bytes.fromhex("ab" * 32)


def test_mask_config_reveal_last_zero_masks_everything() -> None:
    substitute = apply_strategy(_span("245112222"), Strategy.MASK, MaskConfig(reveal_last=0), None)
    assert substitute == "X" * len("245112222")


def test_apply_strategy_rejects_replace_and_surrogate() -> None:
    span = _span()
    with pytest.raises(NotImplementedError):
        apply_strategy(span, Strategy.REPLACE, MaskConfig(), None)
    with pytest.raises(NotImplementedError):
        apply_strategy(span, Strategy.SURROGATE, MaskConfig(), None)
