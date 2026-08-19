"""mask()/unmask() round-trip guarantees, proven with synthetic registered
types -- core ships zero built-in recognizers, so these must hold with no
pack installed at all. See packs/maskflow-pack-intl/tests for the equivalent
coverage using the real EMAIL/PHONE/etc. recognizers.
"""

import re

from maskflow_core.masking import mask, unmask
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
