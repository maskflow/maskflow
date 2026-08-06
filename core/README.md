# maskflow-core

PII detection and reversible masking engine — the foundation for every other MaskFlow phase (CLI, GitHub Action, SDK, ...).

Detects 12 PII types via a three-layer pipeline: regex + structural validation (Luhn for cards, mod-97 for IBANs) -> keyword-context confidence boosting -> spacy NER for names and dates. Overlapping matches are resolved by confidence, and detection returns non-overlapping `Finding`s sorted by position.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd core
uv sync --extra dev
```

## Usage

```python
from maskflow_core import detect, mask, unmask

detect("Email me at alice@example.com or call 415-555-0132.")
# [Finding(type=PIIType.EMAIL, value='alice@example.com', ...), Finding(type=PIIType.PHONE, ...)]

result = mask("Email me at alice@example.com or call 415-555-0132.")
result.masked_text  # "Email me at <EMAIL_1> or call <PHONE_1>."
result.mapping       # {'<EMAIL_1>': 'alice@example.com', '<PHONE_1>': '415-555-0132'}

unmask(result.masked_text, result.mapping)  # original text, restored
```

`mask`/`unmask` are pure functions — the engine never writes to disk or a database. Persisting the mapping is the caller's responsibility (the CLI and SDK phases handle that).

## PII types (v1)

Email, phone, SSN, credit card, IP address (v4/v6), AWS access key, API key / generic secret, JWT, IBAN, street address, person name, date of birth.

## Tests

```bash
uv run pytest
```

`tests/fixtures/pii_samples.py` has 100+ labeled examples; `test_detection.py` enforces a 95% accuracy floor against them and checks that PII-free text produces zero findings.

## Known limitations

- spacy's NER occasionally flags a capitalized sentence-starter as a `PERSON_NAME` false positive (e.g. "Email me at..." -> "Email" tagged as a name). Not a training data issue — future phases add a `.maskflowrc.yml` exclude-config for exactly this kind of false positive.
- Phone/address regexes are US-shaped; international formats are a future improvement.
