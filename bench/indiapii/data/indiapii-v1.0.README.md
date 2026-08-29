# indiapii-v1.0

Synthetic India-PII benchmark corpus for maskflow-pack-india. ALL identifiers in this dataset are synthetic: checksum-valid (Aadhaar, GSTIN) or format-valid (PAN, IFSC, UPI VPA, ...) values generated at random and cross-checked against the pack's own validators (see generator/generate.py's self_check()). **None of these identifiers belong to any real person, business, or account.**

- License: CC-BY-4.0
- Seed: 20260827
- Documents: 2000
- Entity spans: 13468

## Documents per domain

- bank_chat: 285
- hr_record: 286
- insurance_claim: 286
- kyc_form: 286
- loan_application: 285
- medical_note: 286
- support_ticket: 286

## Spans per label

- AADHAAR: 857
- AADHAAR_MASKED: 285
- ABHA_ADDRESS: 141
- ABHA_NUMBER: 286
- BANK_ACCOUNT_IN: 1142
- DRIVING_LICENCE: 286
- GSTIN: 114
- IFSC: 1142
- INDIAN_ADDRESS: 1230
- INDIAN_MOBILE: 1790
- INDIAN_PASSPORT: 101
- NON_VERHOEFF_AADHAAR_SHAPED: 63
- ORDER_ID_SHAPED: 564
- PAN: 857
- PAN_SHAPED_INVOICE_NO: 107
- PERSON_NAME: 2001
- PIN_CODE: 857
- TIMESTAMP_SHAPED: 572
- UPI_VPA: 571
- VEHICLE_REG: 286
- VOTER_ID: 119
- VPA_SHAPED_EMAIL: 97
