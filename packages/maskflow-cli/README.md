# maskflow-cli

Command-line interface for [MaskFlow](https://github.com/):

```
maskflow config validate
maskflow config show --resolved
maskflow doctor
maskflow explain "<text>"
maskflow scan jsonl requests.jsonl --field messages[].content
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

`maskflow scan SOURCE ...` answers one question: **what PII has this system
already sent to third-party LLM providers?** It reads historical LLM traffic
from a source adapter (`jsonl`/`ndjson`, `csv`, `dir`, `s3`, `postgres`, or
the `langfuse`/`helicone`/`langsmith` APIs), streams it through MaskFlow's
detection with bounded memory (`--workers N`, resumable via `--checkpoint`),
and writes **one self-contained HTML file** -- inline CSS/JS, zero external
requests -- with a headline number, breakdowns, a severity ranking, masked
excerpts (never a raw value), and a DPDP Rule 6 mapping appendix. Also
`--format json|csv`. The pattern/checksum pass covers the whole corpus; the
NER pass (names & addresses) runs on `--sample` and is reported as a
labelled estimate unless `--deep` is given. `s3` and `postgres` need the
`maskflow-cli[s3]` / `[postgres]` extras.

    maskflow scan langfuse --since 2026-01-01 --deep -o exposure.html

Runs entirely locally -- API sources only *read* from your own observability
account; nothing is transmitted. See `docs/scan.md` for the full reference.

See `docs/configuration.md` in the repo root for the full config reference.
