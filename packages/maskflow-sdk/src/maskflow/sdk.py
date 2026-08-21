from __future__ import annotations

from collections.abc import Callable

from maskflow_core import unmask
from maskflow_core.config import RootConfig, compile_config
from maskflow_core.detection import DEFAULT_MIN_CONFIDENCE
from maskflow_core.masking import MaskResult, mask_with_policy
from maskflow_core.masking import mask as core_mask

from ._config import get_ambient_config


def mask(
    text: str,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    *,
    config: RootConfig | None = None,
) -> MaskResult:
    """Replace detected PII with `<TYPE_n>` tokens, returning the masked text
    and a {token: original_value} mapping the caller can use to unmask a
    later response.

    With no config active (the default: no .maskflowrc anywhere, and no
    `config=` passed), this is byte-identical to `maskflow_core.mask()` --
    literally the same, untouched function, not just equivalent output.
    When a resolved config *is* active, it can additionally change which
    entities are detected (threshold/enabled/custom patterns/exclusions)
    and how they're substituted (strategy: replace/redact/mask/hash/
    surrogate). Non-reversible substitutions (redact/mask/hash) are simply
    omitted from the returned mapping -- unmask() only touches tokens
    present in it, so this needs no change to MaskResult's shape.

    `config=None` (the default) uses the ambient config discovered from
    the filesystem, cached once per process (see `reload_config()`).
    Passing `config=` explicitly bypasses discovery entirely for this
    call -- the way a library embedded in someone else's application opts
    out of filesystem lookup.
    """
    resolved = config if config is not None else get_ambient_config().config
    compiled = compile_config(resolved)

    if compiled.is_noop():
        return core_mask(text, min_confidence)

    policy_result = mask_with_policy(
        text,
        policy=compiled.policy,
        min_confidence=min_confidence,
        **compiled.detect_kwargs(),
    )
    return MaskResult(
        policy_result.masked_text,
        {
            token: entry.original
            for token, entry in policy_result.mapping.items()
            if entry.reversible
        },
    )


def mask_and_call(
    prompt: str,
    call_fn: Callable[[str], str],
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    *,
    config: RootConfig | None = None,
) -> str:
    """Mask PII in `prompt`, pass the masked text to `call_fn`, and restore the
    original values in whatever `call_fn` returns.

    `call_fn` is any function that takes a string and returns a string --
    typically a closure around an LLM provider's client call. This makes
    mask_and_call provider-agnostic: it works with Claude, OpenAI, Gemini, a
    local model, or anything else, without MaskFlow depending on any
    provider's SDK. See `mask()` for what `config=` does.
    """
    result = mask(prompt, min_confidence=min_confidence, config=config)
    response = call_fn(result.masked_text)
    return unmask(response, result.mapping)
