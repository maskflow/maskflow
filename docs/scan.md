# `maskflow scan` — retrospective PII-exposure scan

`maskflow scan` answers one question, the one a buyer facing the DPDP
deadline asks first:

> **What PII has this system already sent to third-party LLM providers, and
> how bad is it?**

It reads historical LLM traffic from wherever you keep it, runs MaskFlow's
own detection over it with bounded memory, and produces **one
self-contained HTML report** — inline CSS/JS, zero external requests, so it
can be emailed to an auditor on a locked-down machine.

```
maskflow scan SOURCE [TARGET] [options]
```

**Want to see it first?** A synthetic 60-record sample and a walk-through
live in `packages/maskflow-cli/examples/`:

```bash
maskflow scan jsonl packages/maskflow-cli/examples/sample-llm-traffic.jsonl \
  --field 'messages[].content' \
  --provider-field provider --service-field model --timestamp-field created_at \
  --deep --out exposure-report.html
```

(Quote `--field` values — `[]` is a shell glob character.)

> **Runs entirely locally. Nothing is transmitted.** The API sources
> (`langfuse`, `helicone`, `langsmith`) make outbound requests to *your
> own* observability account to *read* your data. No scan data — not the
> traffic, not the findings, not the report — is ever sent anywhere.

## Sources

| SOURCE | TARGET | key options | notes |
|---|---|---|---|
| `jsonl` / `ndjson` | path, or `-` for stdin | `--field` (repeatable) | one JSON object per line |
| `csv` | path | `--columns a,b,c` | header-first CSV |
| `dir` | directory | `--field` and/or `--columns` | recurses; `.jsonl`/`.ndjson`/`.json`/`.csv`/`.txt`/`.log` |
| `s3` | `s3://bucket/prefix` | `--field` | needs `maskflow-cli[s3]`; AWS creds from the standard chain |
| `postgres` | conn string or `$DATABASE_URL` | `--query`, `--columns` | needs `maskflow-cli[postgres]`; `--query` must `ORDER BY` a stable key |
| `langfuse` | — | `--since`, `--until` | `$LANGFUSE_PUBLIC_KEY`, `$LANGFUSE_SECRET_KEY`, `$LANGFUSE_HOST` |
| `helicone` | — | `--since`, `--until` | `$HELICONE_API_KEY` |
| `langsmith` | — | `--since`, `--until` | `$LANGSMITH_API_KEY`, `$LANGSMITH_ENDPOINT` |

### Field selectors (`--field`)

A dotted path with `[]` meaning "every item of this list":

```
--field 'messages[].content'          # every message's .content
--field 'choices[].message.content'   # OpenAI completion shape
--field input                         # a single top-level string
--field data.prompt
```

`--field` is repeatable. Non-string leaves and missing keys are skipped,
never errors — a scan over a heterogeneous dump extracts what it can.

Quote any selector containing `[]` — it is a glob character in bash/zsh, so
an unquoted `messages[].content` fails with "no matches found" before
`maskflow` even runs.

### Attribution

Metadata is best-effort. Point the scanner at the fields that carry it:

```
--provider-field provider   --service-field model
--timestamp-field created_at   --role-field role
--provider openai            # a constant, when the dump doesn't record it
```

(`csv` / `postgres` use `--provider-column` etc. via the same mechanism.)

## Detection depth

The pattern/checksum pass (Aadhaar, PAN, GSTIN, UPI, IFSC, email, phone,
cards, …) runs over the **entire** corpus — this is what hits the
performance target of 1 GB of JSONL in under 5 minutes on a laptop.

The NER pass (bare Indian **names** and **addresses**) is ~100–1000× slower.
By default it runs on a sample of `--ner-sample N` records (default 5 000)
and its name/address counts are **extrapolated and clearly labelled as an
estimate** in the report. Pass `--deep` to run the full pipeline over every
record for exact figures.

The pattern pass runs at roughly 0.4 ms/record per core; with
`--workers 8` on a typical laptop, 1 GB of JSONL (~5 M short records)
finishes in about 4–5 minutes. `--deep` and a large `--ner-sample` trade
directly against that budget — a `--deep` scan of the same 1 GB takes
hours, which is why `--sample` exists for a fast first pass.

If spaCy or its model is not installed, the NER pass is skipped entirely
and the report says so; pattern-based detection is unaffected.

## Streaming, workers, resume

- Inputs are assumed to be gigabytes. Memory is bounded regardless of size:
  the scanner keeps counters, capped distinct-value sets
  (`--distinct-cap`, default 50 000 per entity type), and a reservoir
  sample of masked excerpts (`--excerpt-cap`, default 20).
- `--workers N` (default `min(8, CPU count)`) parallelises detection across
  processes. `--workers 1` runs in-process for debugging.
- `--sample N` caps the total records processed — a fast first pass.
- `--checkpoint FILE` writes an atomic checkpoint every
  `--checkpoint-every` records (default 5 000). Re-running the same command
  resumes from it; the scanner refuses to resume if the source, selectors,
  or detection settings changed (`--restart` to start fresh). The
  checkpoint file contains only PII-free state (counters, HMAC
  fingerprints, masked excerpts) — the same guarantee as the report.

## The report

`--format html` (default) writes one self-contained file:

1. A single **headline number** — total PII instances that reached
   third-party providers.
2. **Breakdowns** by entity type, provider, service/model, and over time.
3. A **severity ranking** — one row per entity type, most severe first,
   each with a one-line plain-English "why this matters".
4. **Masked excerpts** — example contexts with every value shown as a typed
   placeholder such as `<AADHAAR_1>`. A raw value never appears anywhere in
   the document; a permanent CI fuzz job enforces this.
5. **Appendix A — DPDP Rule 6 mapping** — a table skeleton with a
   `<!-- DPDP_RULE6_APPENDIX -->` slot for text maintained by MaskFlow.
6. A **methodology footer** — detector versions, entity list, what was not
   scanned, corpus fingerprint.

`--format json` emits the same data model for diffing/dashboards;
`--format csv` flattens the severity table for spreadsheets. `--out -`
writes to stdout.

## Configuration

`maskflow scan` honours a discovered `.maskflowrc` (or `--config` /
`--set`, exactly like `maskflow explain`), so thresholds, disabled
entities, and exclusions match what a real `mask()` call would do.

## Exit codes

`0` success · `1` bad arguments / invalid config · `2` source
unreachable, auth failure, or checkpoint mismatch.
