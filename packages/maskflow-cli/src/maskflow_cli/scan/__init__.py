"""`maskflow scan` -- retrospective PII-exposure scanner.

Answers one audit question: what PII has this system already sent to
third-party LLM providers, and how bad is it? Reads historical LLM traffic
from a source adapter (jsonl / csv / dir / s3 / postgres / langfuse /
helicone / langsmith), streams it through MaskFlow's own detection with
bounded memory, and writes one self-contained HTML report (or json / csv).

Module map:
  cmd.py         Typer command (thin: parse args -> spec -> run -> render)
  spec.py        SourceSpec + CLI-arg parsing + config fingerprinting
  fieldsel.py    dotted "a.b[].c" path extractor (bounded, no regex)
  sources/       one Source per adapter, behind sources.base.Source
  worker.py      pure per-record detect -> list[FindingSeed] (no I/O, no raw
                 PII crosses back to the parent)
  aggregate.py   bounded streaming Aggregator (counters, capped sets, reservoirs)
  checkpoint.py  atomic, resumable checkpoint file
  severity.py    entity_type -> (Severity, one-line "why this matters")
  pipeline.py    Source -> worker pool -> Aggregator -> Checkpoint orchestration
  report/        Aggregator -> ScanSummary -> html / json / csv
"""

from __future__ import annotations

TRUST_LINE = "Runs entirely locally. Nothing is transmitted."
