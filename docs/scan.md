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
uv run maskflow scan jsonl packages/maskflow-cli/examples/sample-llm-traffic.jsonl \
  --field 'messages[].content' \
  --provider-field provider --service-field model --timestamp-field created_at \
  --deep --out exposure-report.html
```

(`uv run` invokes the CLI from the workspace venv — drop it if
`maskflow-cli` is on your `PATH`. Quote `--field` values — `[]` is a shell
glob character.)

## Install

| | | NER pass (names / addresses / DOB) |
|---|---|---|
| `pipx install maskflow-cli` (or `pip`) | `maskflow scan ...` + `python -m spacy download en_core_web_sm` | yes |
| `docker run --rm -v "$PWD:/work" ghcr.io/maskflow/cli scan ...` | spaCy + model baked in | yes, out of the box |
| standalone binary (GitHub Releases: `maskflow-linux-x86_64`, `-macos-arm64`, `-windows-x86_64.exe`) | no Python needed | **no** — pattern/checksum pass only; `--deep` errors |
| [`maskflow/scan-action`](../packaging/scan-action/) | `maskflow scan` in CI, report as an artifact, optional fail-over threshold | yes |

`s3` / `postgres` sources need the `maskflow-cli[s3]` / `[postgres]` extras
(already in the Docker image). See
[`packages/maskflow-cli/packaging/`](../packages/maskflow-cli/packaging/)
for how each artifact is built.

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
cards, …) runs over the **entire** corpus.

The NER pass (bare Indian **names** and **addresses**) is ~100–1000× slower.
By default it runs on a sample of `--ner-sample N` records (default 5 000)
and its name/address counts are **extrapolated and clearly labelled as an
estimate** in the report. Pass `--deep` to run the full pipeline over every
record for exact figures.

**Throughput.** The pattern pass costs roughly 0.4 ms/record/core on
prose-heavy traffic and up to ~1.3 ms/record/core on pathologically
PII-dense records (measured on a 6-identifiers-per-record synthetic
corpus). With `--workers 8` that puts a **1 GB JSONL export at roughly
5–15 minutes** depending on density — at the low end for real logs, higher
for corpora that are mostly identifiers. Use `--sample N` for a fast first
pass on very large or very dense inputs. `--deep` runs the NER pass over
every record and takes hours on 1 GB — reserve it for a `--sample` or a
modest corpus.

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
5. **Appendix A — DPDP Rule 6 mapping** — a draft mapping of each Rule 6
   safeguard to what the scan / MaskFlow contributes (starting point, not
   legal advice), with a `<!-- DPDP_RULE6_APPENDIX -->` marker for
   substituting your own authoritative text. See
   [`dpdp-rule6.md`](dpdp-rule6.md).
6. A **methodology footer** — detector versions, entity list, what was not
   scanned, corpus fingerprint.

`--format json` emits the same data model for diffing/dashboards;
`--format csv` flattens the severity table for spreadsheets. `--out -`
writes to stdout.

## Measured accuracy on log-shaped input

Detection is benchmarked on prose ([`indiapii-v1.0`](../bench/indiapii/data/),
[`intl-pii-v1.0`](../bench/intlpii/data/)); `scan` runs it over a different shape —
access-log lines, JSON app logs, stack traces, request dumps — dense with PII-lookalike
noise. [`scan-log-v1.0`](../bench/scanbench/data/) is 2 000 synthetic log records
scoring exactly that, with the false-positive rate front and centre because for an
exposure audit a false alarm is the expensive failure. Partial-overlap F1, `--deep`:

| Entity | F1 | | Entity | F1 |
|---|---|---|---|---|
| Aadhaar / PAN / GSTIN / IFSC / UPI VPA | 100% | | Email | 100% |
| Indian mobile | 100% | | JWT / AWS key | 100% |
| Credit card | 97.8% | | API key | 99.7% |
| Person name (`--deep` NER) | 87.9% | | IP address | 66.7%¹ |

**Audit cost — false positives per 1 000 log records:** `--deep` **428** (precision
88%), patterns-only pass **298** (precision 92%), stock Presidio 544 (73%), a naive
regex 433 (79%). The checksum-validated identifiers essentially never false-positive on
log noise — a naive regex flags 337 fake Aadhaars from bare digit runs; MaskFlow flags
0. The residual false positives split between the internal IPs (below) and
`PERSON_NAME`, where the **`--deep` NER pass produces ~2.5× the false names** on log
text (438 vs 178 on the same 2 000 records) — so patterns-only is not just faster but
*more precise* for a scan.

¹ Every internal `10./172.16./192.168.` IP is currently reported as `IP_ADDRESS` — for
an exposure audit a private-range IP is not personal data, and MaskFlow has no
private-IP suppression yet. Known limitation; on the roadmap.

A **plumbing check** in the same benchmark runs the real `run_pipeline(--deep)` over
every record and asserts its aggregated per-entity counts equal what `detect()` finds
directly — so the streaming field-extraction and bounded aggregation are verified not
to drop or double-count a finding. Full table + reproduce command:
[`bench/reports/scan-log-v1.0/results.md`](../bench/reports/scan-log-v1.0/results.md).

## Configuration

`maskflow scan` honours a discovered `.maskflowrc` (or `--config` /
`--set`, exactly like `maskflow explain`), so thresholds, disabled
entities, and exclusions match what a real `mask()` call would do.

## Exit codes

`0` success · `1` bad arguments / invalid config · `2` source
unreachable, auth failure, or checkpoint mismatch.
