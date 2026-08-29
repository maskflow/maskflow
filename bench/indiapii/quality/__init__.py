"""bench/indiapii/quality: does masking India PII before an LLM call cost
task quality, and does it cost more with typed placeholders (<PAN_1>) than
with plausible surrogates?

200 tasks (summarize / draft_reply / extract_fields), sampled from the
existing indiapii-v1.0 corpus (see tasks.py), each run under three
conditions -- unmasked, masked-with-placeholders, masked-with-surrogates
(see pipeline.py) -- scored by a fixed-rubric LLM judge (judge.py) plus
deterministic field accuracy and placeholder-leak detection (scoring.py).
Entry point: `uv run python -m bench.indiapii.quality`.
"""
