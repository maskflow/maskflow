"""Synthetic log corpus generator for bench/scanbench (scan-log-v1.0).

`maskflow scan` runs MaskFlow's detection over *log-shaped* text -- nginx
access lines, structured JSON app logs, multi-line stack traces, LLM
request dumps, worker logs -- which the prose-shaped indiapii-v1.0 /
intl-pii-v1.0 corpora do not exercise. This corpus is that shape, with the
PII-lookalike noise real logs carry (request/trace ids, UUIDs, git SHAs,
epoch-millis timestamps, internal IPs in log position, base64 bearer
blobs, `File.java:142` frames) as hard negatives -- because for a
PII-exposure audit the expensive failure is a *false positive*
("your logs leaked 4,000 Aadhaars" when 3,900 are trace ids).

PII values come from bench.indiapii.generator / bench.intlpii.generator
(checksum-valid where a checksum exists); noise is inserted only around
them, never into an identifier's own characters -- generate.py's
self_check() re-validates every checksum-bearing gold value against the
packs' own validators.
"""
