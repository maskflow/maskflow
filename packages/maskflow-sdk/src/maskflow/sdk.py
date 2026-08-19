from typing import Callable

from maskflow_core import mask, unmask
from maskflow_core.detection import DEFAULT_MIN_CONFIDENCE


def mask_and_call(
    prompt: str,
    call_fn: Callable[[str], str],
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> str:
    """Mask PII in `prompt`, pass the masked text to `call_fn`, and restore the
    original values in whatever `call_fn` returns.

    `call_fn` is any function that takes a string and returns a string --
    typically a closure around an LLM provider's client call. This makes
    mask_and_call provider-agnostic: it works with Claude, OpenAI, Gemini, a
    local model, or anything else, without MaskFlow depending on any
    provider's SDK.
    """
    result = mask(prompt, min_confidence=min_confidence)
    response = call_fn(result.masked_text)
    return unmask(response, result.mapping)
