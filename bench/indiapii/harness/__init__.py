"""Multi-adapter benchmark harness for bench/indiapii's synthetic corpus.

Separate from -- and does not touch -- the sibling `bench/indiapii/metrics.py`
/ `bench/indiapii/report.py`, which track maskflow-pack-india's own L1-L3
fixture accuracy during development. This package answers a different
question: how does MaskFlow compare against Presidio (stock and with hand-
added Aadhaar/PAN recognizers), mask-privacy, a naive regex baseline, and an
LLM asked to extract PII spans, scored per-entity against the same corpus.

The corpus-agnostic scoring core (Document/corpus loading, label
canonicalization, strict/partial-overlap matching, the maskflow adapter,
report writers) moved to the `maskflow-bench` package (issue #36, so
`maskflow bench --my-data <path>` -- packages/maskflow-cli -- can reuse it
without pulling this harness's heavy, optional competitor-adapter
dependencies). See `maskflow_bench.adapters.base` for the Adapter
protocol, `maskflow_bench.corpus` for the dataset loader,
`maskflow_bench.matching` for strict/partial-overlap scoring, and
`maskflow_bench.report` for the JSON/Markdown writers. This package now
only adds the five competitor adapters (adapters/presidio_adapter.py,
adapters/presidio_custom_adapter.py, adapters/mask_privacy_adapter.py,
adapters/naive_regex_adapter.py, adapters/llm_adapter.py) and
build_adapters() (adapters/__init__.py), which assembles all six for the
multi-tool comparison. Entry point: `uv run python -m bench.indiapii.harness`.
"""
