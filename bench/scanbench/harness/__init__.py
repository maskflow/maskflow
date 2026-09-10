"""Benchmark harness for bench/scanbench's log corpus (scan-log-v1.0).

Measures MaskFlow's detection on the input shape `maskflow scan` actually
runs over -- access-log lines, JSON app logs, stack traces, request dumps
-- and, crucially, its **false-positive rate on log noise** (trace ids,
UUIDs, internal IPs, `File.java:142` frames): for a PII-exposure audit the
expensive failure is a false alarm.

The scoring core (corpus loader, strict/partial matching, timed runner,
JSON/Markdown report) is imported wholesale from bench.indiapii.harness.
This package adds the intl+india log-relevant label vocab, the competitor
label maps, two MaskFlow adapters (`detect()` = `--deep`, and
`detect_patterns_only()` = the default fast pass), and a naive-regex
baseline.

`harness/plumbing.py` additionally runs the *real*
`maskflow_cli.scan.pipeline.run_pipeline` over the corpus and asserts its
aggregated per-entity counts equal what `detect()` finds directly -- proof
that field extraction + streaming aggregation lose nothing.

Entry point: `uv run python -m bench.scanbench.harness run`.
"""
