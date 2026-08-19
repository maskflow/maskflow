from maskflow import Finding, MaskResult, PIIType, detect, mask, mask_and_call, unmask


def test_mask_and_call_never_exposes_pii_to_call_fn():
    seen = {}

    def call_fn(masked_prompt: str) -> str:
        seen["prompt"] = masked_prompt
        return f"Sure, I'll email you back at {masked_prompt.split('at ')[1]}"

    prompt = "Email me at alice@example.com with the update."
    mask_and_call(prompt, call_fn)

    assert "alice@example.com" not in seen["prompt"]
    assert "<EMAIL_1>" in seen["prompt"]


def test_mask_and_call_restores_original_values_in_response():
    def call_fn(masked_prompt: str) -> str:
        return f"Got it, confirming: {masked_prompt}"

    prompt = "My phone number is 415-555-0132."
    result = mask_and_call(prompt, call_fn)

    assert "415-555-0132" in result
    assert "<PHONE_1>" not in result


def test_mask_and_call_is_provider_agnostic():
    """call_fn is just a plain callable -- swapping providers means swapping the
    closure, not touching mask_and_call itself."""

    def fake_anthropic_call(masked_prompt: str) -> str:
        return f"[claude] {masked_prompt}"

    def fake_openai_call(masked_prompt: str) -> str:
        return f"[gpt] {masked_prompt}"

    prompt = "Contact bob@example.com."
    assert mask_and_call(prompt, fake_anthropic_call) == f"[claude] {prompt}"
    assert mask_and_call(prompt, fake_openai_call) == f"[gpt] {prompt}"


def test_sdk_reexports_core_primitives():
    text = "Reach me at carol@example.com."
    result = mask(text)

    assert isinstance(result, MaskResult)
    assert unmask(result.masked_text, result.mapping) == text
    assert detect(text)[0].type == PIIType.EMAIL
    assert isinstance(detect(text)[0], Finding)
