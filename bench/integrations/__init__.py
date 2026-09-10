"""Integration-parity harness.

The four framework integrations -- `maskflow-litellm`, `maskflow-langchain`,
`maskflow-llamaindex`, `maskflow-mcp` -- each wrap `maskflow`'s masking
engine to fit a framework's data shapes. Every one has unit tests, but
nothing checks, over a realistic PII-dense corpus, that routing text
through the wrapper:

1. masks **exactly** the `(entity_type, value)` set the core engine does --
   no spurious wrapper detections, nothing dropped walking message /
   node / argument structures;
2. round-trips **byte-exact** through the wrapper's own unmask path;
3. survives a streamed response split at arbitrary byte boundaries
   (litellm / llamaindex ship a `StreamingUnmasker`-based path).

These are equality assertions against the `core` reference, not drifting
metrics -- a divergence is always a wrapper bug. The corpus is a subset of
`bench/indiapii/data/indiapii-v1.0.jsonl`.

Entry point: `uv run python -m bench.integrations run`
(needs `uv sync --all-extras --group litellm --group llama-index --group mcp`).
"""
