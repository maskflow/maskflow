# MaskFlow

Indian PII detection and reversible masking for LLM pipelines. Aadhaar, PAN, GSTIN, UPI, IFSC,
names — masked before a prompt leaves your process, restored in the response.

[![CI](https://github.com/maskflow/maskflow/actions/workflows/ci.yml/badge.svg)](https://github.com/maskflow/maskflow/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/maskflow-sdk)](https://pypi.org/project/maskflow-sdk/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Quickstart

```bash
pip install maskflow-sdk
```

```python
from maskflow import mask, unmask

result = mask("Email me at alice@example.com or call 415-555-0132.")
result.masked_text
# "Email me at <EMAIL_1> or call <PHONE_1>."
unmask(result.masked_text, result.mapping)  # original text, restored
```

## Configuration

Drop a `.maskflowrc` (TOML/YAML/JSON) in your project to adjust entity thresholds, disable an
entity, add a custom regex-based entity, exclude specific values, or change the substitution
strategy (replace/redact/mask/hash/surrogate) — `mask()`/`mask_and_call()`/`session()` all pick it
up automatically, with no `.maskflowrc` anywhere behaving exactly as before this existed:

```toml
[entities.PHONE]
strategy = "mask"          # "415-555-0132" -> "XXX-XXX-0132" instead of "<PHONE_1>"

[custom.EMPLOYEE_ID]
pattern = '\bEMP-\d{6}\b'
score = 0.9
```

```bash
pip install maskflow-cli   # maskflow config validate / maskflow config show --resolved
```

See [`docs/configuration.md`](docs/configuration.md) for the full schema and precedence rules.

## What it detects today

`maskflow-sdk` and `maskflow-cli` both bundle `maskflow-pack-intl` and `maskflow-pack-india` —
installing either gets you everything below with no extra install step:

| Type | How |
|---|---|
| Email | Regex |
| Phone | Regex |
| SSN | Regex + area-code validation |
| Credit card | Regex + Luhn checksum |
| IP address (v4/v6) | Regex |
| AWS access key | Regex |
| API key / generic secret | Regex |
| JWT | Regex |
| IBAN | Regex + mod-97 checksum |
| Street address | Regex |
| Person name | spaCy NER |
| Date of birth | spaCy NER + keyword context |
| Aadhaar (UID + VID) | Regex + Verhoeff checksum |
| Aadhaar (masked display form, e.g. `XXXX XXXX 9012`) | Regex, unvalidated, needs context |
| PAN | Regex + holder-category structural check (no public final-letter checksum) |
| GSTIN | Regex + state-code range + embedded-PAN check + base-36 checksum |
| IFSC | Regex + bank code against a bundled RBI code list |
| UPI VPA | Regex + PSP handle against a bundled NPCI handle list |

ABHA and Indian names/addresses are not yet implemented.

## MaskFlow vs. alternatives

|  | MaskFlow | Presidio | mask-privacy |
|---|---|---|---|
| Indian identifiers with checksums | Aadhaar, PAN, GSTIN, IFSC, UPI (in `maskflow-sdk`) | No | No |
| Session-consistent tokens (unmask later) | Yes | Via custom anonymizer config | Yes, today |
| NER | spaCy | spaCy, Stanza, transformers | Regex-based, no NER |
| Breadth / maturity | Narrow, early (12 types) | Broad, mature (Microsoft-backed, years of production use) | Narrow, early |
| License | MIT | MIT | Varies by package |
| Languages | Python (JS port in progress) | Python, multi-language via configurable NLP models | JS/TS |

Presidio is ahead on breadth and maturity. If you need broad, battle-tested coverage today, use it.
MaskFlow's bet is Indian-identifier accuracy and a reversible mask/unmask flow that's simpler to
drop into a single-provider-agnostic call.

## Benchmark

Open benchmark coming: per-entity precision/recall, open dataset, reproducible — including results
where competitors beat us.

## Links

- Site: [maskflow.in](https://maskflow.in)
- Docs: [packages/maskflow-sdk/README.md](packages/maskflow-sdk/README.md),
  [docs/configuration.md](docs/configuration.md) (`.maskflowrc`)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
