# indiapii-tabular-v1.0

Synthetic Indian-PII **tables**: the output a coding agent or an analyst
actually handles (`psql`, `mysql`, `sqlite3 -header`, CSV/TSV exports,
markdown tables). It measures whether MaskFlow masks a value when the only
thing saying what it is sits in the column header, often hundreds of rows
above it.

ALL identifiers are synthetic. They come from the IndiaPII-v1.0 generators
(`bench/indiapii/generator/identifiers.py`), so they are checksum-valid
(Aadhaar) or format-valid (PAN, IFSC, UPI, ...). **None belongs to a real
person, business or account.**

- License: CC-BY-4.0
- Seed: 20261014
- Documents: 300 (50 per format: csv, tsv, psql, mysql, markdown, sqlite)
- Rows per table: 3, 5, 12, 40 or 120
- Labelled spans: 26,062

## Spans per label

| label | spans |
|---|---|
| AADHAAR | 3,327 |
| BANK_ACCOUNT_IN | 3,251 |
| IFSC | 3,205 |
| INDIAN_MOBILE | 3,697 |
| PAN | 3,327 |
| PERSON_NAME | 2,982 |
| PIN_CODE | 3,272 |
| UPI_VPA | 3,001 |

Mobile numbers, Aadhaar numbers and account numbers are written bare (no
`+91`, no separators), the way a database stores them.

## Decoy columns

Every table can also carry up to two **unlabelled** decoy columns holding
values shaped like PII that aren't PII:

| headers | values |
|---|---|
| `order_id`, `txn_ref`, `invoice_no`, `ticket` | 10 digits starting 6–9 (mobile-shaped) |
| `account_id`, `user_account_id`, `account_type_code` | 11 digits (bank-account-shaped) |
| `mobile_app_build`, `phone_model_code`, `test_mobile`, `sample_phone` | 10 digits starting 6–9 |
| `amount`, `balance` | decimal amounts |

A prediction inside a decoy column counts as a false positive, so precision
here measures whether MaskFlow over-masks look-alike columns.

## Reproduce

```bash
uv run python -m bench.tabular.generate          # regenerate (byte-identical)
uv run python -m bench.tabular.score             # score -> bench/reports/indiapii-tabular-v1.0/
uv run pytest bench/tabular/tests -q             # reproducibility + F1 gate
```

## Known limit

A random 12–18 digit account number sometimes passes the Luhn check
(→ `CREDIT_CARD`) or Aadhaar's Verhoeff check (→ `AADHAAR`). A
checksum-validated span always wins over an unvalidated one (a core design
rule), so those cells are masked under the wrong type. They are still
masked, but they count as a BANK_ACCOUNT_IN miss. That is most of the
remaining BANK_ACCOUNT_IN recall gap and the AADHAAR false positives.
