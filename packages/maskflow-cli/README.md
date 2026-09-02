# maskflow-cli

Command-line interface for [MaskFlow](https://github.com/):

```
maskflow config validate
maskflow config show --resolved
maskflow doctor
maskflow explain "<text>"
maskflow scan jsonl requests.jsonl --field 'messages[].content'
```

`maskflow doctor` checks installed versions, spaCy model presence (and
which entities that consequently disables), and `.maskflowrc` validity,
then reports enabled/disabled status for every registered entity. It
exits 0 only when every check passes.

`maskflow explain "<text>"` shows, span by span, why each piece of text
was (or wasn't) detected as PII -- the pattern/NER hit, checksum result,
context boost, and the threshold decision behind it. Spans that scored
below their entity's threshold are listed separately as NEAREST MISSES,
with the `.maskflowrc` change that would catch them. Matched text is
truncated to 8 characters unless `--full` is passed. Accepts the same
`--config`/`--set` overrides as `maskflow config`, so explanations reflect
the same resolved config a real `mask()` call would use.

## `maskflow scan` -- what PII already reached your LLM providers

`maskflow scan SOURCE ...` answers the question a DPDP-deadline audit asks
first: **what PII has this system already sent to third-party LLM
providers, and how bad is it?** It reads your historical LLM traffic, runs
MaskFlow's own detection over it, and writes **one self-contained HTML
report** -- inline CSS/JS, zero external requests, so it prints cleanly and
can be emailed to an auditor as-is.

**Features**

- **Eight source adapters**, one interface: `jsonl` / `ndjson` (with
  `--field` selectors), `csv` (`--columns`), `dir` (recursive), `s3`
  (streamed), `postgres` (server-side cursor), and the `langfuse` /
  `helicone` / `langsmith` REST APIs. `s3` and `postgres` need the
  `maskflow-cli[s3]` / `[postgres]` extras; the rest need nothing extra.
- **Streaming, bounded memory** -- inputs can be gigabytes. `--workers N`
  parallelises detection; `--checkpoint FILE` makes a run resumable;
  `--sample N` is a fast first pass.
- **Hybrid detection.** The pattern/checksum pass (Aadhaar, PAN, GSTIN,
  UPI, IFSC, cards, email, ...) covers the whole corpus. The NER pass
  (bare names & addresses) runs on a sample and is reported as a clearly
  labelled estimate -- pass `--deep` to run it over everything.
- **The report**: one headline number, breakdowns by entity type /
  provider / model / time, a severity ranking with a plain-English "why
  this matters" per row, **masked excerpts only** (values shown as
  `<AADHAAR_1>`, never raw), and a DPDP Rule 6 mapping appendix. Also
  `--format json|csv`.
- **Runs entirely locally. Nothing is transmitted.** The API sources only
  *read* from your own observability account.

**Try it** -- a synthetic 60-record sample ships in
[`examples/`](examples/):

```bash
maskflow scan jsonl packages/maskflow-cli/examples/sample-llm-traffic.jsonl \
  --field 'messages[].content' \
  --provider-field provider --service-field model --timestamp-field created_at \
  --deep --out exposure-report.html
```

Quote the `--field` value -- `messages[].content` contains `[]`, which your
shell would otherwise try to expand.

Then open `exposure-report.html`. See [`examples/README.md`](examples/README.md)
for a walk-through of the output, and `docs/scan.md` for the full reference.

See `docs/configuration.md` in the repo root for the full config reference.
