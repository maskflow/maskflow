# @maskflow/detection

PII detection and reversible masking, in TypeScript. A port of `core`'s regex/structural
detection layer -- shares the same API shape as the Python SDK.

```ts
import { mask, unmask } from "@maskflow/detection";

const result = mask("Email me at alice@example.com or call 415-555-0132.");
result.maskedText; // "Email me at <EMAIL_1> or call <PHONE_1>."
result.mapping;     // { "<EMAIL_1>": "alice@example.com", "<PHONE_1>": "415-555-0132" }

unmask(result.maskedText, result.mapping); // original text, restored
```

## Scope

Covers the 10 PII types that are pure regex + structural validation (Luhn, mod-97, etc.): email,
phone, SSN, credit card, IP address, AWS key, API key, JWT, IBAN, street address.

`PERSON_NAME` and `DATE_OF_BIRTH` are **not** included -- those need spaCy's NER, which has no
practical browser/Node equivalent here. They stay Python-only, in `core`.

## Why a separate package

This logic is meant to be shared by more than one consumer -- the marketing site's live demo
today, potentially a Chrome extension or a TypeScript SDK later -- without duplicating (and
silently drifting from) the same regex rules in each place.

## Tests

Runs against the same fixtures as `core`'s Python test suite (`scripts/generate_js_fixtures.py`
regenerates `tests/fixtures.json` from the Python source of truth), so both implementations are
held to the same accuracy bar.

```bash
npm test -w @maskflow/detection
```
