---
license: cc-by-4.0
language:
  - en
  - hi
pretty_name: IndiaPII-Bench v1.0
tags:
  - pii
  - privacy
  - ner
  - india
  - synthetic
  - benchmark
task_categories:
  - token-classification
size_categories:
  - 1K<n<10K
---

# IndiaPII-Bench v1.0

A synthetic, adversarial, labelled benchmark for Indian PII detection: Aadhaar, PAN, GSTIN, IFSC,
UPI VPA, ABHA, Indian mobile numbers, addresses, names, and more. Built for
[MaskFlow](https://github.com/maskflow/maskflow), the free, open-source PII masking library for
LLM pipelines, but usable to evaluate any Indian-PII detector.

## ⚠️ Synthetic data — read before using

**Every identifier in this dataset is synthetic.** Aadhaar and GSTIN values are generated with
mathematically valid checksums (Verhoeff, GSTIN mod-36); PANs, IFSC codes, and the rest are
structurally valid. **None of them belong to any real person, business, or account.** Values are
generated at random and cross-checked against
[maskflow-pack-india](https://github.com/maskflow/maskflow/tree/main/packs/maskflow-pack-india)'s
own validators as part of the build (`self_check()` in
[`generate.py`](https://github.com/maskflow/maskflow/blob/main/bench/indiapii/generator/generate.py)) —
proof that "checksum-valid" is actually true of what was generated, not merely asserted.

## Dataset summary

- **2,000 documents**, **13,468 labelled entity spans**
- 7 document domains: support ticket, KYC form, insurance claim, medical note, HR record, bank
  chat transcript, loan application
- Deterministic build (seed `20260827`) — anyone can regenerate this exact corpus
- Hinglish / code-mixed text, Devanagari + Latin script mixing, and messaging-style noise in the
  conversational domains (bank chat, support ticket)
- **Labelled hard negatives**: PII-shaped values that are *not* real PII (a non-Verhoeff 12-digit
  number, a PAN-shaped invoice number, a VPA-shaped email, order IDs, timestamps) — these are what
  make precision measurable, not just recall

## Documents per domain

| Domain | Count |
|---|---|
| bank_chat | 285 |
| hr_record | 286 |
| insurance_claim | 286 |
| kyc_form | 286 |
| loan_application | 285 |
| medical_note | 286 |
| support_ticket | 286 |

## Entity taxonomy

### Positive labels (real PII, scored for recall)

| Label | Description | Spans |
|---|---|---|
| `AADHAAR` | 12-digit Indian national ID (Aadhaar), may be spaced/hyphenated in groups of 4 | 857 |
| `AADHAAR_MASKED` | Aadhaar number with first 8 digits masked, only last 4 digits visible | 285 |
| `ABHA_ADDRESS` | Ayushman Bharat Health Account address, email-shaped (e.g. `name@abdm`) | 141 |
| `ABHA_NUMBER` | 14-digit Ayushman Bharat Health Account number | 286 |
| `BANK_ACCOUNT_IN` | Indian bank account number, 9–18 digits | 1,142 |
| `DRIVING_LICENCE` | Indian driving licence number (state code + digits) | 286 |
| `GSTIN` | 15-character Goods and Services Tax Identification Number | 114 |
| `IFSC` | 11-character bank branch code (4 letters + 0 + 6 alphanumeric) | 1,142 |
| `INDIAN_ADDRESS` | A residential/postal address in India (street, locality, city, state) | 1,230 |
| `INDIAN_MOBILE` | Indian mobile phone number, 10 digits, optionally with `+91` prefix | 1,790 |
| `INDIAN_PASSPORT` | Indian passport number (1 letter + 7 digits) or its MRZ block | 101 |
| `PAN` | 10-character Permanent Account Number (5 letters + 4 digits + 1 letter) | 857 |
| `PERSON_NAME` | A person's full name | 2,001 |
| `PIN_CODE` | 6-digit Indian postal PIN code | 857 |
| `UPI_VPA` | UPI Virtual Payment Address, looks like `username@bank-handle` | 571 |
| `VEHICLE_REG` | Indian vehicle registration number (state code + district + series + digits) | 286 |
| `VOTER_ID` | Voter ID / EPIC number, 3 letters + 7 digits | 119 |

### Hard-negative labels (PII-shaped, never real PII, scored against false positives)

| Label | Description | Spans |
|---|---|---|
| `NON_VERHOEFF_AADHAAR_SHAPED` | A 12-digit number formatted like Aadhaar but failing the Verhoeff checksum | 63 |
| `ORDER_ID_SHAPED` | An order/reference number that resembles a structured identifier | 564 |
| `PAN_SHAPED_INVOICE_NO` | An invoice number in PAN's 5-letters-4-digits-1-letter shape | 107 |
| `TIMESTAMP_SHAPED` | An ISO-style timestamp long enough to be mistaken for a numeric ID | 572 |
| `VPA_SHAPED_EMAIL` | An email address in `local@domain` form, shaped like a UPI VPA | 97 |

A detector that flags a hard-negative span is not penalized for missing it (it was never gold),
but *is* penalized for the false positive it produced — this is what makes the benchmark's
precision numbers meaningful, not just its recall.

## Data format

One JSON object per line:

```json
{
  "id": "indiapii-v1.0-00001",
  "text": "...",
  "domain": "insurance_claim",
  "lang": "en",
  "entities": [
    {"start": 47, "end": 64, "label": "PERSON_NAME", "value_class": "positive"}
  ]
}
```

`entities[].value_class` is `"positive"` (real, gold PII — scored for recall) or `"hard_negative"`
(PII-shaped decoy — scored only against false positives, never gold).

## Generation method

Built by a deterministic template-and-identifier generator
([`bench/indiapii/generator/`](https://github.com/maskflow/maskflow/tree/main/bench/indiapii/generator)):
domain templates are filled with synthetic identifiers generated to pass (positives) or
deliberately fail (hard negatives) each type's real validator, then noise (Hinglish code-mixing,
script mixing, messaging-style abbreviation) is layered on top. A single `random.Random(seed)`
instance threads through the whole run, so `--seed 20260827 --count 2000` reproduces this exact
corpus byte-for-byte.

## Known limitations

- **Realism noise is uneven across domains.** The conversational domains (bank chat, support
  ticket) carry real Hinglish code-mixing and typos; the structured-form domains (KYC form, loan
  application, insurance claim) are still clean `Field: value` layouts with little noise applied.
  Treat scores on the form domains as an upper bound relative to real-world messiness.
- Synthetic text, generated from templates — even with noise applied, it will not fully capture
  the diversity of real documents.
- English and Hinglish only; no dedicated Devanagari-only documents.

## Intended use

Evaluating and comparing Indian-PII detectors (regex/checksum, NER, LLM-based) — this is the
dataset behind MaskFlow's own published benchmark
([`bench/reports/indiapii-v1.0/results.md`](https://github.com/maskflow/maskflow/blob/main/bench/reports/indiapii-v1.0/results.md)).
Not intended, and not suitable, for training a model to generate real-looking Indian identifiers.

## Reproduction

```bash
git clone https://github.com/maskflow/maskflow
cd maskflow
uv sync --all-extras
uv run python bench/indiapii/generator/generate.py --count 2000 \
    --out bench/indiapii/data/indiapii-v1.0.jsonl
```

Score any detector against it (MaskFlow's own detector, no extra setup needed):

```bash
pip install 'maskflow-cli[bench]'
maskflow bench --my-data bench/indiapii/data/indiapii-v1.0.jsonl
```

## Citation

```bibtex
@dataset{maskflow_indiapii_bench_2026,
  title        = {IndiaPII-Bench v1.0},
  author       = {Sodani, Somya},
  year         = {2026},
  publisher    = {Hugging Face},
  howpublished = {\url{https://huggingface.co/datasets/maskflow-ai/indiapii-bench}},
  license      = {CC-BY-4.0}
}
```

## License

CC-BY-4.0. Attribution: MaskFlow project (https://github.com/maskflow/maskflow).
