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

Both register the `PIIType` itself first if it isn't already known, and are idempotent-safe to
call from any installed pack's `__init__.py`.

## Tests

```bash
uv run pytest packages/maskflow-core/tests
```

Core's own tests use synthetic registered types throughout (not any pack's real recognizers), so
they hold with no pack installed at all. See `packs/maskflow-pack-intl/tests` for the 12-type
accuracy suite.
