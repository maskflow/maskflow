# intl-pii-v1.0

Synthetic international-PII benchmark corpus for `maskflow-pack-intl`. ALL values in this dataset are synthetic: checksum-valid (CREDIT_CARD via Luhn, IBAN via mod-97), drawn from real-but-never-assigned ranges (SSN area numbers, the NANP `555-01xx` fiction range for phone numbers), or structurally valid to their published format with no real-world backing (EMAIL, AWS_KEY, API_KEY, JWT, IP_ADDRESS, ADDRESS, PERSON_NAME, DATE_OF_BIRTH). Every checksum-bearing value is cross-checked against the pack's own validators by `generator/generate.py`'s `self_check()`. **None of these values belong to any real person, account, or credential.**

- License: CC-BY-4.0
- Seed: 20260910
- Documents: 1800
- Entity spans (gold, positive only): 9368
- Decoy spans (hard negatives, never gold): 971

## Documents per domain

- crm_note: 360
- incident_report: 360
- invoice_email: 360
- signup_form: 360
- support_ticket: 360

## Spans per label

- ADDRESS: 1080
- API_KEY: 360
- AWS_KEY: 360
- CREDIT_CARD: 512
- DATE_OF_BIRTH: 360
- EMAIL: 2160
- IBAN: 493
- IP_ADDRESS: 360
- JWT: 256
- ORDER_ID_SHAPED: 718
- PERSON_NAME: 2160
- PHONE: 1080
- SSN: 187
- TRACKING_NUMBER_SHAPED: 253

## Entity taxonomy (gold)

- ADDRESS
- API_KEY
- AWS_KEY
- CREDIT_CARD
- DATE_OF_BIRTH
- EMAIL
- IBAN
- IP_ADDRESS
- JWT
- PERSON_NAME
- PHONE
- SSN

## Known limitations

- English only; no code-mixed or OCR'd input (that discipline lives in `indiapii-v1.0`).
- `PERSON_NAME` and `DATE_OF_BIRTH` depend on the spaCy NER pass; recall on them reflects `en_core_web_sm`, not a ceiling.
- `API_KEY` covers OpenAI / Anthropic / GitHub / Google shapes; no Slack `xox*` token -- a random one still trips GitHub's push-protection scanner. The pack's `API_KEY_RE` covers that branch; this corpus does not.
- Generic PII is not a surface MaskFlow competes on (Presidio / mask-privacy own it). This corpus exists to publish a measured number, not to claim a win.

## Citation

```
MaskFlow intl-pii-v1.0 synthetic international-PII benchmark corpus. MIT-licensed project, CC-BY-4.0 dataset. https://github.com/maskflow/maskflow
```
