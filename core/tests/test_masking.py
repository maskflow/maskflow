from maskflow_core.masking import mask, unmask


def test_mask_replaces_pii_with_tokens():
    text = "Email me at alice@example.com or call 415-555-0132."
    result = mask(text)

    assert "alice@example.com" not in result.masked_text
    assert "415-555-0132" not in result.masked_text
    assert "<EMAIL_1>" in result.masked_text
    assert "<PHONE_1>" in result.masked_text
    assert result.mapping["<EMAIL_1>"] == "alice@example.com"
    assert result.mapping["<PHONE_1>"] == "415-555-0132"


def test_unmask_round_trips_exactly():
    text = (
        "Hi, this is Jane Doe. My email is jane.doe@example.com and my phone is "
        "415-555-0198. My SSN is 245-11-2222 for the background check."
    )
    result = mask(text)
    assert unmask(result.masked_text, result.mapping) == text


def test_mask_numbers_tokens_of_same_type_sequentially():
    text = "Contact alice@example.com or bob@example.com."
    result = mask(text)

    assert result.mapping["<EMAIL_1>"] == "alice@example.com"
    assert result.mapping["<EMAIL_2>"] == "bob@example.com"


def test_mask_is_idempotent_on_clean_text():
    text = "This sentence has no PII in it at all."
    result = mask(text)

    assert result.masked_text == text
    assert result.mapping == {}
