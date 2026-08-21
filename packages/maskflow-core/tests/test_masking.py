"""mask()/unmask() round-trip guarantees, proven with synthetic registered
types -- core ships zero built-in recognizers, so these must hold with no
pack installed at all. See packs/maskflow-pack-intl/tests for the equivalent
coverage using the real EMAIL/PHONE/etc. recognizers.
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st
from maskflow_core.masking import mask, mask_with_policy, unmask
from maskflow_core.policy import MaskPolicy
from maskflow_core.registry import register_pattern

MARKER_A_RE = re.compile(r"\bMARK-A-\d{4}\b")
MARKER_B_RE = re.compile(r"\bMARK-B-\d{4}\b")

register_pattern("TEST_MARKER_A", MARKER_A_RE, 0.95)
register_pattern("TEST_MARKER_B", MARKER_B_RE, 0.95)


def test_mask_replaces_pii_with_tokens() -> None:
    text = "Ref MARK-A-1111 and MARK-B-2222 in your reply."
    result = mask(text)

    assert "MARK-A-1111" not in result.masked_text
    assert "MARK-B-2222" not in result.masked_text
    assert "<TEST_MARKER_A_1>" in result.masked_text
    assert "<TEST_MARKER_B_1>" in result.masked_text
    assert result.mapping["<TEST_MARKER_A_1>"] == "MARK-A-1111"
    assert result.mapping["<TEST_MARKER_B_1>"] == "MARK-B-2222"


def test_unmask_round_trips_exactly() -> None:
    text = "Hi, this is a note. Ref MARK-A-1111 and MARK-B-2222 for the background check."
    result = mask(text)
    assert unmask(result.masked_text, result.mapping) == text


def test_mask_numbers_tokens_of_same_type_sequentially() -> None:
    text = "Refs MARK-A-1111 and MARK-A-3333."
    result = mask(text)

    assert result.mapping["<TEST_MARKER_A_1>"] == "MARK-A-1111"
    assert result.mapping["<TEST_MARKER_A_2>"] == "MARK-A-3333"


def test_mask_is_idempotent_on_clean_text() -> None:
    text = "This sentence has no PII in it at all."
    result = mask(text)

    assert result.masked_text == text
    assert result.mapping == {}


def test_unmask_round_trips_with_emoji() -> None:
    text = "📧 Ref MARK-A-1111 👍 or MARK-B-2222 📞 thanks!"
    result = mask(text)
    assert unmask(result.masked_text, result.mapping) == text


def test_unmask_round_trips_with_rtl_text() -> None:
    text = "مرحبا بك، راسلني على MARK-A-1111 من فضلك"
    result = mask(text)
    assert unmask(result.masked_text, result.mapping) == text


def test_unmask_round_trips_with_zero_width_characters() -> None:
    zwsp = "​"  # zero-width space
    zwj = "‍"  # zero-width joiner
    text = f"Ref{zwsp} MARK-A-1111{zwj} please reach out"
    result = mask(text)
    assert unmask(result.masked_text, result.mapping) == text


def test_unmask_round_trips_with_mixed_unicode_and_multiple_entities() -> None:
    zwsp = "​"
    zwj = "‍"
    text = f"👋 مرحبا{zwsp} Ref: MARK-A-1111{zwj} Other: MARK-B-2222 🎉"
    result = mask(text)
    assert unmask(result.masked_text, result.mapping) == text


def test_mask_avoids_colliding_with_placeholder_lookalike_text() -> None:
    text = "Please keep the literal token <TEST_MARKER_A_1> as-is. Ref MARK-A-1111."
    result = mask(text)

    # The real marker's assigned token must not be the colliding
    # "<TEST_MARKER_A_1>" -- it must fall back to a nonce form instead.
    assert "<TEST_MARKER_A_1>" not in result.mapping
    assert "MARK-A-1111" not in result.masked_text
    assert unmask(result.masked_text, result.mapping) == text


def test_mask_avoids_colliding_with_lookalike_immediately_adjacent() -> None:
    # The lookalike token butts right up against the real match (no
    # whitespace boundary) -- an adversarial variant of the collision case
    # above, checking the reserved-token scan isn't relying on word
    # boundaries around the lookalike to find it.
    text = "<TEST_MARKER_A_1>MARK-A-1111"
    result = mask(text)

    assert "<TEST_MARKER_A_1>" not in result.mapping
    assert "MARK-A-1111" not in result.masked_text
    assert unmask(result.masked_text, result.mapping) == text


def test_mask_reuses_the_same_token_for_a_repeated_value() -> None:
    text = "Ref MARK-A-1111, again MARK-A-1111, and MARK-B-2222."
    result = mask(text)

    assert result.masked_text.count("<TEST_MARKER_A_1>") == 2
    assert "<TEST_MARKER_A_2>" not in result.masked_text
    assert result.mapping == {
        "<TEST_MARKER_A_1>": "MARK-A-1111",
        "<TEST_MARKER_B_1>": "MARK-B-2222",
    }
    assert unmask(result.masked_text, result.mapping) == text


def test_unmask_round_trips_empty_string() -> None:
    result = mask("")
    assert unmask(result.masked_text, result.mapping) == ""


def test_unmask_round_trips_pii_at_index_zero() -> None:
    text = "MARK-A-1111 is the reference to quote back."
    result = mask(text)
    assert result.masked_text.startswith("<TEST_MARKER_A_1>")
    assert unmask(result.masked_text, result.mapping) == text


def test_unmask_round_trips_pii_at_final_index() -> None:
    text = "Please quote this reference back: MARK-A-1111"
    result = mask(text)
    assert result.masked_text.endswith("<TEST_MARKER_A_1>")
    assert unmask(result.masked_text, result.mapping) == text


def test_unmask_round_trips_with_combining_characters() -> None:
    # "é" as base "e" + combining acute accent (U+0301), not the precomposed
    # form -- a byte-offset scheme would risk splitting this apart.
    combining_e = "é"
    text = f"Référence {combining_e}: MARK-A-1111 {combining_e} merci"
    result = mask(text)
    assert unmask(result.masked_text, result.mapping) == text


@settings(max_examples=10_000)
@given(st.text())
def test_roundtrip_property(t: str) -> None:
    """CLAUDE.md rule 5, 'round-trip sacred': unmask(mask(t).masked_text,
    mapping) == t exactly, for any input text at all -- not just the
    hand-picked cases above."""
    r = mask(t)
    assert unmask(r.masked_text, r.mapping) == t


@settings(max_examples=10_000)
@given(st.text(), st.floats(min_value=0.0, max_value=1.0))
def test_mask_with_policy_default_matches_mask(t: str, min_confidence: float) -> None:
    """The hard guarantee PR 2's .maskflowrc wiring leans on: an all-default
    MaskPolicy() through mask_with_policy() must produce byte-identical
    output to mask() -- for any text and any min_confidence, not just the
    hand-picked cases above. This is what makes maskflow-sdk's config-aware
    mask() wrapper safe to delegate to mask_with_policy() (Part 4) instead
    of re-deriving mask()'s substitution/collision logic, and is also what
    makes the "no .maskflowrc anywhere" byte-identical requirement hold for
    an *explicitly* passed default config, not just the config=None case.
    """
    plain = mask(t, min_confidence=min_confidence)
    policy_result = mask_with_policy(t, MaskPolicy(), min_confidence=min_confidence)

    assert policy_result.masked_text == plain.masked_text
    reversible_mapping = {
        token: entry.original
        for token, entry in policy_result.mapping.items()
        if entry.reversible
    }
    assert reversible_mapping == plain.mapping
