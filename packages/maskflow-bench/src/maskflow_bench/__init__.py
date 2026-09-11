"""maskflow-bench: the corpus-agnostic PII-detection scoring core.

Loads a labelled JSONL corpus into `Document` objects (corpus.py),
canonicalizes its entity taxonomy (labels.py), scores an adapter's raw
(start, end, label) predictions against it under strict-span and
partial-overlap matching (matching.py), times and profiles that run
(profiling.py, runner.py), and writes `results.json`/`results.md`
(report.py).

This package has exactly one built-in adapter, `adapters.maskflow_adapter.
MaskflowAdapter` (wraps `maskflow_core.detection.detect`, zero extra
third-party dependencies) -- the `loader`/`scorer` modules on top of it are
what `maskflow bench --my-data <path>` (packages/maskflow-cli) uses to
score MaskFlow against a user's own labelled documents.

It is also the shared implementation behind bench/indiapii/harness's,
bench/intlpii/harness's, and bench/scanbench/harness's own dev-only,
multi-adapter comparisons (Presidio, mask-privacy, naive regex, an LLM
judge) used to produce the published IndiaPII-Bench-style figures -- those
adapters, and the harness CLIs that run all of them together, stay in
bench/ since they pull heavy, optional third-party dependencies this
package never needs.
"""

from __future__ import annotations
