# MaskFlow

**Stop Indian PII from ever reaching an LLM.**

Aadhaar, PAN, GSTIN, UPI, IFSC, ABHA, Indian names and addresses — detected and replaced with
reversible, typed placeholders before a prompt leaves your process, restored in the response.
28 entity types, checksum-validated where a public checksum exists, MIT-licensed, runs entirely
on your own infrastructure.

[![CI](https://github.com/maskflow/maskflow/actions/workflows/ci.yml/badge.svg)](https://github.com/maskflow/maskflow/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/maskflow-sdk)](https://pypi.org/project/maskflow-sdk/)
[![npm](https://img.shields.io/npm/v/%40maskflow%2Fdetection)](https://www.npmjs.com/package/@maskflow/detection)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

<p align="center">
  <img src=".github/assets/demo.svg" alt="Terminal demo: pip install maskflow-sdk, then mask() replaces an Aadhaar number and email with &lt;AADHAAR_1&gt; and &lt;EMAIL_1&gt; before an LLM call, and unmask() restores the originals in the response" width="720">
</p>

## Why

India's DPDP Act sets a compliance deadline of **13 May 2027**, with penalties of up to
**₹250 crore** for a breach where the required safeguards weren't in place. Every prompt sent to
an LLM provider is a potential data-sharing event — and general-purpose PII tools weren't built to
recognize Aadhaar, PAN, GSTIN, UPI VPAs, IFSC codes, ABHA health IDs, or Indian names and addresses
reliably. [Presidio](https://github.com/microsoft/presidio) already owns generic PII and is more
mature everywhere else; MaskFlow exists specifically to close that gap, with accuracy that's
measured and published, not asserted. See [MaskFlow vs. alternatives](#maskflow-vs-alternatives).

## Quickstart

```bash
pip install maskflow-sdk
python -m spacy download en_core_web_sm
```

```python
from maskflow import mask, unmask

result = mask("My Aadhaar is 2346 8907 6543 and you can reach me at alice@example.com.")
result.masked_text
# "My Aadhaar is <AADHAAR_1> and you can reach me at <EMAIL_1>."
unmask(result.masked_text, result.mapping)  # original text, restored
```

For a one-line wrapper around your actual LLM call, or session-scoped masking across a multi-turn
agent (same value → same token for as long as the session is open), see
[`packages/maskflow-sdk/README.md`](packages/maskflow-sdk/README.md).

## How it works

1. **Tier-0 excision first.** Deterministic regex/checksum matches (Aadhaar, PAN, GSTIN, email,
   credit card, ...) are found and locked in *before* the NER pass ever runs — spaCy parses each
   document at most once, only over what tier-0 didn't already claim.
2. **Every match is a `Span`.** Start/end offsets, entity type, confidence, which recognizer
   produced it, whether a checksum validated it, and a human-readable explanation trail. Run
   `maskflow explain "<text>"` (from `maskflow-cli`) to see that trail for any input, span by span
   — including near-misses that fell just below threshold and what config change would catch them.
3. **Deterministic resolution on overlaps.** Below-threshold spans are dropped; among what's left,
   a checksum-validated span always beats an overlapping unvalidated one, then higher confidence,
   then longer span, then earliest start wins — greedy, non-overlapping placement.
4. **Placeholders are typed, stable, and collision-proof.** `<AADHAAR_1>`, `<EMAIL_1>`, ... — the
   same value gets the same token within a session, and if the input text already contains
   something that looks like a placeholder, a nonce suffix (`<AADHAAR_1_a4f9>`) is used instead so
   a real placeholder is never ambiguous with attacker-controlled input.
5. **Recognizers are pluggable.** `maskflow-pack-intl` and `maskflow-pack-india` are just two
   `"maskflow.recognizers"` entry-point plugins sharing one memoised analysis context — write and
   register your own the same way. See [`docs/custom-recognizers.md`](docs/custom-recognizers.md).

## Protecting your own logs

Regex/checksum-based recognizers can also scrub your application's own `logging` calls — not just
text passed through `mask()` — closing the gap where a raw value gets logged before it's ever
masked:

```python
from maskflow_core import install_pii_filter

install_pii_filter()  # attaches to the root logger, once, at startup
```

Opt-in only; importing `maskflow_core` never touches global logging state on its own. It doesn't
cover NER-only entity types (bare names/addresses) or `exc_info` tracebacks — see
[`docs/logging.md`](docs/logging.md) for the exact boundary.

## Auditing what already reached a provider

Going forward, `mask()` keeps PII out of your prompts. But the DPDP audit asks a backward-looking
question first: *what has this system already sent to a third-party LLM?* `maskflow scan` answers
it. It reads your historical LLM traffic — a JSONL/CSV export, a recursive directory, an S3
archive, a Postgres table, or the Langfuse / Helicone / LangSmith API — streams it through the
same detection with bounded memory (parallel, resumable), and writes **one self-contained HTML
report**: a single headline number, breakdowns by entity type / provider / model / time, a
severity ranking with a plain-English "why this matters" per row, **masked excerpts only** (never
a raw value), and a DPDP Rule 6 mapping appendix. Also `--format json|csv`. Runs entirely locally
— the API sources only *read* from your own account, nothing is transmitted.

```bash
pipx install maskflow-cli   # or: docker run --rm -v "$PWD:/work" ghcr.io/maskflow/cli
maskflow scan jsonl requests.jsonl --field 'messages[].content' --deep -o exposure.html
```

Also ships as a standalone binary (mac/linux/windows, no Python — pattern pass only) and a
[GitHub Action](packaging/scan-action/) that can fail a build over a PII-exposure threshold. A
runnable 60-record synthetic example is in
[`packages/maskflow-cli/examples/`](packages/maskflow-cli/examples/); full reference,
including the Rule 6 mapping, in [`docs/scan.md`](docs/scan.md).

## Configuration

Drop a `.maskflowrc` (TOML/YAML/JSON) in your project to adjust entity thresholds, disable an
entity, add a custom regex-based entity, exclude specific values, or change the substitution
strategy per entity (`replace` / `redact` / `mask` / `hash` / `surrogate` — the last swaps in a
plausible *fake* value drawn from reserved/test-only ranges, e.g. RFC 2606 example domains or
publicly documented payment-industry test card numbers, instead of a placeholder token).
`mask()`/`mask_and_call()`/`session()` all pick it up automatically; no `.maskflowrc` anywhere
behaves exactly as before this existed:

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
installing either gets you all 28 types below with no extra install step.

**International (12 types)** — `maskflow-pack-intl`:

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

**Indian (17 types, the moat)** — `maskflow-pack-india`:

| Type | How |
|---|---|
| Aadhaar (UID + VID) | Regex + Verhoeff checksum |
| Aadhaar (masked display form, e.g. `XXXX XXXX 9012`) | Regex, unvalidated, needs context |
| PAN | Regex + holder-category structural check (no public final-letter checksum) |
| GSTIN | Regex + state-code range + embedded-PAN check + base-36 checksum |
| IFSC | Regex + bank code against a bundled RBI code list |
| UPI VPA | Regex + PSP handle against a bundled NPCI handle list |
| Indian mobile number | Regex, full confidence with a `+91`/`0` prefix, needs context otherwise |
| PIN code | Regex, unvalidated, needs context (pin/pincode/state name/address) |
| Voter ID (EPIC number) | Regex, structural only (no public checksum) |
| Indian passport number | Regex, structural only (no public checksum) |
| Indian passport MRZ block | Regex + 4 ICAO 9303 check digits |
| Driving licence | Regex + state RTO code against a bundled code list |
| Vehicle registration | Regex + state RTO code against a bundled code list |
| ABHA number (health ID) | Regex, unvalidated, needs context |
| ABHA address | Regex + domain (abdm/sbx) check |
| Bank account number (India) | Regex, unvalidated, needs context (account/a/c/acct) |
| Person name (Indian) | Gazetteer (name corpus) + structural (honorifics, relational markers, initials, form fields) + spaCy NER agreement boost |
| Indian address | Gazetteer (554+ Indian cities/places) + structural (unit markers, landmark-relative phrasing, locality patterns) |

(`PERSON_NAME` is one shared entity type produced by both packs' layers, so 12 + 17 − 1 shared = 28
unique types total.)

## Multi-language

`@maskflow/detection` on npm is a TypeScript port of the 10 pure regex/structural intl types
(email, phone, SSN, credit card, IP, AWS key, API key, JWT, IBAN, street address) — same API
shape as the Python SDK, tested against the same fixtures so both stay accuracy-matched.
`PERSON_NAME`/`DATE_OF_BIRTH` (need spaCy NER) and the India pack's checksum-validated types stay
Python-only for now. See [`packages/maskflow-js/README.md`](packages/maskflow-js/README.md).

```ts
import { mask, unmask } from "@maskflow/detection";

const result = mask("Email me at alice@example.com or call 415-555-0132.");
unmask(result.maskedText, result.mapping); // original text, restored
```

## MaskFlow vs. alternatives

|  | MaskFlow | Presidio | mask-privacy |
|---|---|---|---|
| Indian identifiers with checksums | Aadhaar, PAN, GSTIN, IFSC, UPI (in `maskflow-sdk`) | No | No |
| Session-consistent tokens (unmask later) | Yes | Via custom anonymizer config | Yes, today |
| NER | spaCy | spaCy, Stanza, transformers | Regex-based, no NER |
| Breadth / maturity | Narrow, early (28 types) | Broad, mature (Microsoft-backed, years of production use) | Narrow, early |
| License | MIT | MIT | Varies by package |
| Languages | Python + TypeScript (regex layer) | Python, multi-language via configurable NLP models | JS/TS |

Presidio is ahead on breadth and maturity. If you need broad, battle-tested coverage today, use it.
MaskFlow's bet is Indian-identifier accuracy and a reversible mask/unmask flow that's simpler to
drop into a single, provider-agnostic call.

## Benchmark

Real numbers, not vendor claims — including results where competitors beat us. Scored on
[`indiapii-v1.0`](bench/indiapii/data/indiapii-v1.0.jsonl), 2000 synthetic, checksum-valid
documents (Aadhaar/PAN/GSTIN pass the same validity math the real formats use), against stock
Presidio, Presidio with two hand-added Aadhaar/PAN recognizers, and mask-privacy. F1 below is
partial-overlap matching (exact-character matching is too strict for multi-token spans like
addresses — see the full report for both).

| Entity | MaskFlow | Presidio (stock) | Presidio + custom | mask-privacy |
|---|---|---|---|---|
| GSTIN / IFSC / UPI VPA | 100% | not supported | not supported | not supported |
| AADHAAR | 98.4% | not supported | 96.6% | not supported |
| PAN | 100% | not supported | 100% | not supported |
| Indian mobile number | 99.0% | 94.9% | 94.9% | 41.9% |
| Person name | 47.3% | 30.4% | 30.4% | 37.7% |
| Indian address | 43.3% | 48.2% | 48.2% | **57.9%** |

Indian address is the one row above where a competitor is ahead — our gazetteer still has room to
grow, and we're not hiding that. Full per-entity breakdown (all 17 types), strict-vs-partial
matching, and latency/memory numbers:
[`bench/reports/indiapii-v1.0/results.md`](bench/reports/indiapii-v1.0/results.md). Reproduce with
`uv sync --group bench && uv run python -m bench.indiapii.harness run`; harness source in
[`bench/indiapii/harness/`](bench/indiapii/harness/).

## Roadmap

Openly not done yet, so you know what you're signing up for:

- `maskflow-gateway` — an HTTP proxy that masks/unmasks around any provider without touching
  application code. Not started; see `CLAUDE.md`'s target architecture.
- Full India-pack parity in `@maskflow/detection` (checksum-validated Indian types, not just the
  10 intl regex types).

## Links

- Site: [maskflow.in](https://maskflow.in)
- Docs: [`docs/configuration.md`](docs/configuration.md),
  [`docs/custom-recognizers.md`](docs/custom-recognizers.md),
  [`docs/scan.md`](docs/scan.md), [`docs/dpdp-rule6.md`](docs/dpdp-rule6.md),
  [`docs/agent-sessions.md`](docs/agent-sessions.md), [`docs/logging.md`](docs/logging.md),
  [`docs/data-refresh.md`](docs/data-refresh.md)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- License: [MIT](LICENSE)
