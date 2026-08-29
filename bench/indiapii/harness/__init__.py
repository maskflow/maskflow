"""Multi-adapter benchmark harness for bench/indiapii's synthetic corpus.

Separate from -- and does not touch -- the sibling `bench/indiapii/metrics.py`
/ `bench/indiapii/report.py`, which track maskflow-pack-india's own L1-L3
fixture accuracy during development. This package answers a different
question: how does MaskFlow compare against Presidio (stock and with hand-
added Aadhaar/PAN recognizers), mask-privacy, a naive regex baseline, and an
LLM asked to extract PII spans, scored per-entity against the same corpus.

See adapters/base.py for the Adapter protocol, corpus.py for the dataset
loader, matching.py for strict/partial-overlap scoring, and report.py for
the JSON/Markdown writers. Entry point: `uv run python -m bench.indiapii.harness`.
"""
