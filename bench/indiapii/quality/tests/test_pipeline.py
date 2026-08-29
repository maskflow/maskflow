"""run_condition() wiring, tested against a fake model (no network/API key
needed) that just echoes whatever prompt it was given back verbatim -- lets
us assert the masking/unmasking plumbing is correct without ever calling
Anthropic. TaskModel.generate() itself (the real network path) is exercised
only by a live `run` invocation, same as harness/adapters/llm_adapter.py's
own untested-by-CI network call.
"""

from __future__ import annotations

from dataclasses import dataclass

from bench.indiapii.quality.pipeline import run_condition


@dataclass
class _EchoModel:
    """Fakes TaskModel: returns the document it was given, unchanged --
    lets a test assert exactly what got masked without a real LLM call."""

    def generate(self, instruction: str, document: str) -> str:
        return document


def test_unmasked_condition_sends_raw_text_untouched() -> None:
    text = "Contact PAN holder ABCPE1234F for verification."
    result = run_condition(_EchoModel(), "unmasked", "irrelevant", text)
    assert result.prompt_sent == text
    assert result.final_response == text
    assert not result.had_leak


def test_placeholder_condition_masks_and_restores() -> None:
    text = "Contact PAN holder ABCPE1234F for verification."
    result = run_condition(_EchoModel(), "placeholder", "irrelevant", text)
    assert "ABCPE1234F" not in result.prompt_sent
    assert "<PAN_1>" in result.prompt_sent
    # The echo model reflects the masked text back unchanged, so unmask()
    # must restore the original value exactly.
    assert result.final_response == text
    assert not result.had_leak


def test_surrogate_condition_masks_with_a_different_valid_value() -> None:
    text = "Contact PAN holder ABCPE1234F for verification."
    result = run_condition(_EchoModel(), "surrogate", "irrelevant", text)
    assert "ABCPE1234F" not in result.prompt_sent
    assert result.final_response == text
    assert not result.had_leak


class _DropsPlaceholderModel:
    """Fakes a model that forgets to echo the placeholder token back --
    simulates the leak scenario had_leak is meant to catch."""

    def generate(self, instruction: str, document: str) -> str:
        return "Verification pending, no reference number available."


def test_leak_detected_when_placeholder_is_dropped_before_unmask() -> None:
    text = "Contact PAN holder ABCPE1234F for verification."
    result = run_condition(_DropsPlaceholderModel(), "placeholder", "irrelevant", text)
    assert not result.had_leak  # nothing leaked -- the token was dropped, not left in


class _HallucinatesTokenModel:
    """Fakes a model that writes a placeholder-shaped token no mapping
    entry actually assigned (e.g. mis-numbered it) -- unmask() only
    replaces tokens it knows about, so this one survives into the final
    text unchanged, which is exactly the leak had_leak exists to catch."""

    def generate(self, instruction: str, document: str) -> str:
        return "See <PAN_9> for the account on file."


def test_leak_flagged_when_an_unmapped_placeholder_token_survives() -> None:
    text = "Account holder PAN ABCPE1234F"
    result = run_condition(_HallucinatesTokenModel(), "placeholder", "irrelevant", text)
    assert "<PAN_9>" in result.final_response
    assert result.had_leak
