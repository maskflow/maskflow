# maskflow-core

PII detection and reversible masking **engine** — the foundation every other MaskFlow package
builds on. Ships with **zero recognizers**: no PII type is built in. `detect()`/`mask()`/
`unmask()` work against whatever types a pack has registered via `register_pattern()` (regex +
structural validation) or `register_ner_recognizer()` (spaCy entity labels), with keyword-context
confidence boosting and central overlap resolution shared by both. See
[`maskflow-pack-intl`](../../packs/maskflow-pack-intl) for the original 12 intl/US-shaped
recognizers, or [`maskflow-sdk`](../maskflow-sdk) for a ready-to-use package that bundles them.

## Install

Requires [uv](https://docs.astral.sh/uv/). This package is part of a uv workspace — run from the
**repo root**:

```bash
uv sync --all-extras
```

spaCy is optional (`maskflow-core[nlp]`) — without it, any pack's NER-based recognizers are
disabled with a single warning; pattern-based (regex) recognizers are unaffected. If you do want
NER, the model is a separate download rather than a pip dependency (PyPI doesn't allow packages
to declare a direct URL as a dependency):

```bash
uv run python -m spacy download en_core_web_sm
```

## Usage

Core alone detects nothing until something registers a recognizer:

```python
import re
from maskflow_core import detect, mask, unmask
from maskflow_core.registry import register_pattern

register_pattern("WIDGET_ID", re.compile(r"\bWID-\d{6}\b"), base_confidence=0.9)

detect("Reference WID-123456 in your reply.")
# [Span(entity_type='WIDGET_ID', ...)]

result = mask("Reference WID-123456 in your reply.")
result.masked_text  # "Reference <WIDGET_ID_1> in your reply."
unmask(result.masked_text, result.mapping)  # original text, restored
```

In practice, most users won't call `register_pattern`/`register_ner_recognizer` directly — they
install a pack (`maskflow-pack-intl`, and later `maskflow-pack-india`) that does it on import.

`mask`/`unmask` are pure functions — the engine never writes to disk or a database. Persisting
the mapping is the caller's responsibility (the CLI and SDK phases handle that).

## Extension points

- `register_pattern(pii_type, regex, base_confidence, validator=None, context_keywords=None)` —
  a regex-based recognizer, optionally gated by a structural validator (Luhn, mod-97, ...) and/or
  boosted by nearby keywords.
- `register_ner_recognizer(spacy_label, pii_type, base_confidence, threshold=0.0, context_keywords=None)`
  — maps one spaCy entity label onto a PII type.
- `register_surrogate_generator(pii_type, generator, note)` — a `Strategy.SURROGATE` fake-value
  generator for a type (see below); `note` documents the reserved/invalid range or corpus it
  draws from.

All three register the `PIIType` itself first if it isn't already known, and are idempotent-safe
to call from any installed pack's `__init__.py`.

## Masking strategies

`mask()`/`unmask()` (above) are frozen as `maskflow-sdk`'s public API and always use
`Strategy.REPLACE` — a typed `<TYPE_n>` placeholder, fully reversible. For more control, use
`mask_with_policy()` alongside them:

```python
from maskflow_core import MaskPolicy, PIIType, Strategy, mask_with_policy, unmask

policy = MaskPolicy(
    default_strategy=Strategy.REPLACE,
    per_entity_strategy={PIIType.register("SSN"): Strategy.REDACT},
)
result = mask_with_policy("Contact WID-123456, SSN 245-11-2222.", policy)
result.masked_text  # "Contact <WIDGET_ID_1>, SSN [REDACTED_SSN]."
unmask(result.masked_text, result.mapping)  # SSN stays redacted -- see below
```

Five strategies, selected per entity type via `MaskPolicy`:

| Strategy | Output | Reversible via `unmask()`? |
|---|---|---|
| `REPLACE` (default) | typed placeholder, e.g. `<EMAIL_1>` | yes |
| `SURROGATE` | a plausible fake of the same type/shape (falls back to `REPLACE` if no generator is registered for that type) | yes |
| `REDACT` | a constant `[REDACTED_TYPE]` marker | no |
| `MASK` | partial reveal, e.g. `XXXX XXXX 9012` (`MaskConfig(reveal_last, mask_char)`) | no |
| `HASH` | HMAC-SHA256 hex digest, stable per value (`HashConfig(key=...)` or `MASKFLOW_HASH_KEY` env, hex-encoded) | no |

`REPLACE` and `SURROGATE` substitute a unique per-instance value the LLM will echo back verbatim,
so `unmask()` can find and restore it. `REDACT`/`MASK`/`HASH` are intentionally lossy — the
`MappingEntry` still records the original for audit purposes, but `unmask()` leaves that
substituted text as-is rather than guessing which original it came from.

`mask_with_policy()` returns a `PolicyMaskResult` whose `.mapping` is a `Mapping` (token ->
`MappingEntry`, not a plain dict) — `MappingEntry.original` is repr-excluded, same discipline as
`Span.text`.

## Mapping persistence

`mask()`/`mask_with_policy()` are pure — the mapping never touches disk on its own. To persist one
across requests/processes, use a `MappingStore`:

```python
from maskflow_core import EncryptedFileMappingStore, InMemoryMappingStore

store = InMemoryMappingStore(ttl_seconds=3600)  # default: process-local, TTL-expiring
store.save("session-123", result.mapping)
store.load("session-123")

# AES-GCM at rest -- requires `maskflow-core[store]`, key from MASKFLOW_MAPPING_KEY (hex) or passed explicitly
store = EncryptedFileMappingStore("/var/run/maskflow-mappings")
```

`RedisMappingStore` exists as an interface-only stub (constructor + method shapes only) — every
method raises `NotImplementedError` until a real implementation ships.

## Tests

```bash
uv run pytest packages/maskflow-core/tests
```

Core's own tests use synthetic registered types throughout (not any pack's real recognizers), so
they hold with no pack installed at all. See `packs/maskflow-pack-intl/tests` for the 12-type
accuracy suite.
