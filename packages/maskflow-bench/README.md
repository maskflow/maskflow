# maskflow-bench

The scoring core behind MaskFlow's accuracy measurements: load a labelled
JSONL corpus, canonicalize its entity taxonomy, score detections under
strict-span and partial-overlap precision/recall/F1, write `results.json`
and `results.md`.

Most people reach this through `maskflow bench --my-data <path>`
(`maskflow-cli`) — see [`docs/bench.md`](../../docs/bench.md) for the
labelled-data schema and command reference.

This package intentionally ships **one** adapter — MaskFlow itself
(`adapters.maskflow_adapter.MaskflowAdapter`) — with no dependency beyond
`maskflow-core`. The multi-adapter comparison against Presidio,
mask-privacy, a naive-regex baseline, and an LLM judge that produced the
published IndiaPII-Bench tables lives in `bench/indiapii/harness/` (repo
dev tooling, not published), and imports this package for the parts that
don't change per adapter.
