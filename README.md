# MaskFlow

Indian PII detection and reversible masking for LLM pipelines. Aadhaar, PAN, GSTIN, UPI, IFSC,
names — masked before a prompt leaves your process, restored in the response.

[![CI](https://img.shields.io/badge/CI-pending-lightgrey)](#)
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

## What it detects today

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

India pack (Aadhaar, PAN, GSTIN, UPI, IFSC, ABHA, Indian names) in active development.

## MaskFlow vs. alternatives

|  | MaskFlow | Presidio | mask-privacy |
|---|---|---|---|
| Indian identifiers with checksums | In development (Aadhaar, PAN, GSTIN) | No | No |
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
- Docs: [sdk/python/README.md](sdk/python/README.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
