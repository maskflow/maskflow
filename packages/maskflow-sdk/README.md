# maskflow

Mask PII before it reaches an LLM. Unmask the response. Works with any provider.

```python
from maskflow import mask_and_call


def call_claude(masked_prompt: str) -> str:
    return (
        anthropic_client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": masked_prompt}],
        )
        .content[0]
        .text
    )


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

For more control than the wrapper gives, `mask`/`unmask` are available directly. Persisting the
mapping between calls is your responsibility -- neither function uses a database, but `mask()`
does read a `.maskflowrc` if one is discovered (see "Configuration" below); pass `config=` to
skip that lookup entirely.

```python
from maskflow import mask, unmask

result = mask("Email me at alice@example.com.")
result.masked_text  # "Email me at <EMAIL_1>."
result.mapping  # {"<EMAIL_1>": "alice@example.com"}

unmask(result.masked_text, result.mapping)  # original text, restored
```

## Session-scoped masking

`mask()` restarts its token numbering on every call, so two separate calls can each hand out
`<PHONE_1>` for two *different* phone numbers -- fine for one-shot use, wrong for a multi-turn
agent that needs the same value to keep the same token across calls. `session()` fixes that by
keeping value->token identity stable for as long as it's open:

```python
import maskflow

with maskflow.session() as s:
    prompt = s.mask(user_input)
    args = s.mask_json(tool_call_arguments)  # masks string leaves only, keys untouched
    reply = s.unmask(llm_response)
```

Sessions are closeable (`with ... as s:` or `s.close()`) and TTL-bounded (`ttl_seconds`, default
3600 seconds); either purges the mapping. `maskflow.async_session()` is the `asyncio` counterpart.
Neither is thread-safe. See [`docs/agent-sessions.md`](../../docs/agent-sessions.md) for the
concrete before/after this fixes.

## Configuration (`.maskflowrc`)

`mask()`, `mask_and_call()`, and `session()`/`async_session()` all read a `.maskflowrc` file
automatically if one is discovered on disk -- no code change needed to adjust entity thresholds,
disable an entity, add a custom regex-based entity, exclude specific values, or change the
substitution strategy (replace/redact/mask/hash/surrogate). Pass `config=` to bypass discovery and
supply one explicitly:

```python
import maskflow
from maskflow_core.config import RootConfig, EntityConfig
from maskflow_core.strategies import Strategy

result = maskflow.mask(
    "Reach me at alice@example.com.",
    config=RootConfig(entities={"EMAIL": EntityConfig(strategy=Strategy.MASK)}),
)
```

With no `.maskflowrc` anywhere and no `config=` passed, behavior is unchanged from before this
feature existed. See [`docs/configuration.md`](../../docs/configuration.md) for the full schema,
precedence rules, and `maskflow.reload_config()` (forces a fresh discovery in a long-running
process, which otherwise caches the discovered config once per process).

## What gets detected

Email, phone, SSN, credit card, IP address, AWS access key, API key / generic secret, JWT, IBAN,
street address, person name, date of birth -- via regex + structural validation (Luhn, mod-97,
etc.) plus spaCy NER for names and dates, with keyword-context confidence boosting. These 12
recognizers ship in [`maskflow-pack-intl`](../../packs/maskflow-pack-intl), which `maskflow-sdk`
depends on automatically; the engine itself lives in [`maskflow-core`](../maskflow-core) and
ships with none built in.

## Tests

```bash
uv run pytest
```
