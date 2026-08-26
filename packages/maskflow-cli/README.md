# maskflow-cli

Command-line interface for [MaskFlow](https://github.com/):

```
maskflow config validate
maskflow config show --resolved
maskflow doctor
maskflow explain "<text>"
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

See `docs/configuration.md` in the repo root for the full config reference.
