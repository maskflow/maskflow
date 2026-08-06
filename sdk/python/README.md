# maskflow

Mask PII before it reaches an LLM. Unmask the response. Works with any provider.

```python
from maskflow import mask_and_call

def call_claude(masked_prompt: str) -> str:
    return anthropic_client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": masked_prompt}],
    ).content[0].text

response = mask_and_call(
    "Hi, I'm Jane Doe (jane@example.com). My order shipped to 123 Main St but never arrived.",
    call_claude,
)
# Claude only ever sees "Hi, I'm <PERSON_NAME_1> (<EMAIL_1>). My order shipped to
# <ADDRESS_1> but never arrived." -- response comes back with the real values restored.
```

## Install

```bash
pip install maskflow-sdk
python -m spacy download en_core_web_sm
```

## Why this shape

`mask_and_call` takes a plain function, not a specific provider's client. You write the one line
that actually calls your LLM (Claude, OpenAI, Gemini, a local model, anything) -- maskflow never
parses or depends on any provider's SDK, so it doesn't break when a provider changes their API and
works with providers it's never heard of.

```python
response = mask_and_call(prompt, lambda masked: my_llm_client.generate(masked))
```

## Lower-level API

For more control than the wrapper gives, `mask`/`unmask` are available directly and are pure,
stateless functions -- no files, no database. Persisting the mapping between calls is your
responsibility.

```python
from maskflow import mask, unmask

result = mask("Email me at alice@example.com.")
result.masked_text  # "Email me at <EMAIL_1>."
result.mapping       # {"<EMAIL_1>": "alice@example.com"}

unmask(result.masked_text, result.mapping)  # original text, restored
```

## What gets detected

Email, phone, SSN, credit card, IP address, AWS access key, API key / generic secret, JWT, IBAN,
street address, person name, date of birth -- via regex + structural validation (Luhn, mod-97,
etc.) plus spaCy NER for names and dates, with keyword-context confidence boosting. See
[`maskflow-core`](../../core) for detection internals.

## Tests

```bash
uv run pytest
```
