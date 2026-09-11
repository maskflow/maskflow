# `maskflow bench --my-data` — is it accurate on *your* documents?

The published IndiaPII-Bench numbers ([`bench/reports/`](../bench/reports/))
are measured on a synthetic corpus. That's necessary for a reproducible,
shareable benchmark, but it is still someone else's documents. `maskflow
bench --my-data <path>` runs the same scoring MaskFlow uses internally
against **your own** labelled file and prints per-entity
precision/recall/F1 — so "is it accurate on my documents?" has a command,
not an argument.

```
maskflow bench --my-data PATH [--out DIR] [--limit N]
```

- `--my-data PATH` (required) — your labelled JSONL file, one document per
  line.
- `--out DIR` (optional) — also writes `results.json` and `results.md`
  into `DIR`, in the same shape the published benchmark reports use.
- `--limit N` (optional) — score only the first `N` lines. Useful as a
  quick smoke test before running the whole file.

This scores **MaskFlow only**. It is not the six-way comparison against
Presidio, mask-privacy, a naive-regex baseline, and an LLM judge that
produced the tables in the main README's [Benchmark](../README.md#benchmark)
section and [`bench/reports/`](../bench/reports/) — that comparison is repo
dev tooling (`bench/indiapii/harness/`, `uv sync --group bench`), not
something `maskflow-cli` ships.

## File format

One JSON object per line. Only two fields are required:

```json
{"text": "Please update my PAN ABCDE1234F on file.", "entities": [{"start": 22, "end": 32, "label": "PAN"}]}
```

- `text` (string, required) — the document.
- `entities` (list, required) — the spans you've labelled as PII in
  `text`. Each entry needs:
  - `start`, `end` (integers) — character offsets into `text`, Python
    slice semantics (`text[start:end]` is the value).
  - `label` (string) — the entity type. Use whatever name you want for
    your own review, but it only lines up with a MaskFlow detection if it
    matches one of MaskFlow's own type names (`AADHAAR`, `PAN`, `GSTIN`,
    `IFSC`, `UPI_VPA`, `PERSON_NAME`, `INDIAN_ADDRESS`, ... — see the
    README's [What it detects today](../README.md#what-it-detects-today)
    for the full list, or `maskflow doctor` for what's enabled in your
    environment).

Everything else is optional, with defaults chosen so a file with no idea
of MaskFlow's benchmark conventions still works:

| Field | Default | Notes |
|---|---|---|
| `id` | `"line-<N>"` | For your own reference; doesn't affect scoring. |
| `domain` | `"user_data"` | Free text, not used for scoring. |
| `lang` | `"en"` | Free text, not used for scoring. |
| `entities[].value_class` | `"positive"` | See "Hard negatives" below. |

A malformed line produces a clear, line-numbered error (`PATH:line N: ...`)
and a non-zero exit code — never a raw Python traceback.

### Hard negatives

If you have examples of things that *look* like PII but aren't —
something shaped like a PAN that's actually an invoice number, an
email-shaped VPA that isn't a real UPI handle — label them with
`"value_class": "hard_negative"`. They're never counted as a miss if
MaskFlow doesn't flag them, but a false hit on one still costs precision.
This is what makes precision a meaningful number rather than "did it find
everything" alone. If you don't care about this, just omit the field —
every entity defaults to a real positive.

```json
{"text": "invoice INV-0001 paid", "entities": [{"start": 8, "end": 16, "label": "PAN_SHAPED", "value_class": "hard_negative"}]}
```

## Reading the output

```
Entity    Strict P   Strict R   Strict F1   Partial P   Partial R   Partial F1
────────────────────────────────────────────────────────────────────────────
IFSC          0.0%       0.0%        0.0%      100.0%      100.0%       100.0%
```

- **Strict** — the predicted span must match your labelled `start`/`end`
  exactly.
- **Partial** — any overlap with your labelled span counts, as long as
  the type matches. More forgiving of small offset disagreements.
- **`0.0%`** is a *measured* zero — MaskFlow made a prediction for that
  type, but it didn't match. **`—`** means the metric is undefined: no
  prediction and no gold span for that type at all, so there was nothing
  to score.

`--out DIR`'s `results.json` follows the same schema as every other
`bench/reports/*/results.json` in this repo, under a single `"maskflow"`
key — so the same tooling that reads the published reports reads yours.
