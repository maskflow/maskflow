# `maskflow scan` example

`sample-llm-traffic.jsonl` is **60 fully synthetic** LLM API request records
— the kind of log a team might export from an OpenAI/Anthropic gateway or an
observability tool. About three quarters of them contain planted PII
(Aadhaar, PAN, GSTIN, UPI VPA, IFSC, Indian mobile, passport, driving
licence, credit card, date of birth, names, postal addresses); the rest are
clean support queries.

> **Nothing here is real.** Every identifier is generated to be
> checksum-/format-valid but drawn at random within that shape — never from
> or against a real registry. Names, emails (`@*.example`), and addresses are
> assembled from synthetic pools. See `generate_sample.py`.

Each record looks like:

```json
{"request_id": "req_0007", "provider": "anthropic", "model": "claude-sonnet-4",
 "created_at": "2026-03-20T14:05:00Z",
 "messages": [{"role": "user", "content": "Run a KYC check for ... Aadhaar ... PAN ..."}]}
```

## Run it

From the repo root (or anywhere, with `maskflow-cli` installed):

```bash
maskflow scan jsonl packages/maskflow-cli/examples/sample-llm-traffic.jsonl \
  --field 'messages[].content' \
  --provider-field provider \
  --service-field model \
  --timestamp-field created_at \
  --deep \
  --out exposure-report.html
```

- `--field 'messages[].content'` — pull the text out of each record (the `[]`
  means "every message"). **Quote it** — `[]` is a glob character in most
  shells, so an unquoted `messages[].content` fails with "no matches found".
- `--provider-field` / `--service-field` / `--timestamp-field` — map the
  record's metadata columns so the report can break exposure down by
  provider, model, and time.
- `--deep` — run the full pipeline (names and addresses included) over every
  record. Fine here because the file is tiny; on a real multi-GB corpus you
  would drop `--deep` and let the NER pass run on a sample.
- `--out` — where to write the report. `--format json` or `--format csv`
  give you the same data as structured output instead.

Open `exposure-report.html` in a browser. It is a single self-contained file
— no network, no external assets — so it prints cleanly and can be emailed
as-is.

## What the report shows

For this sample you should see roughly:

- **~165 PII instances** reached three providers (openai, anthropic,
  google), across **~49 of 60** records.
- A breakdown by entity type — Aadhaar, PAN, passport, and credit card land
  in the **Critical** severity band; addresses, driving licences, DOB, UPI
  in **High**; names, mobiles, email, GSTIN in **Medium**; IFSC in **Low**.
- A per-day time series and a per-provider / per-model split.
- Expandable **masked** example contexts under each severity row — the
  values are shown only as typed placeholders like `<AADHAAR_1>`, never
  raw.
- An **Appendix A** slot for the DPDP Rule 6 mapping.

## Regenerate

```bash
uv run python packages/maskflow-cli/examples/generate_sample.py
```

Deterministic (fixed seed), so the committed file only changes when the
generator does.
