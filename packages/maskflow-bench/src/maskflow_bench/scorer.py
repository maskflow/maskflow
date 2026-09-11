"""Scores MaskFlow itself against a user's own labelled data
(`maskflow bench --my-data <path>`). Thin composition of loader.py +
labels.py + runner.py + adapters.maskflow_adapter -- the same pieces
bench/indiapii/harness/__main__.py assembles ad hoc for the bundled
corpora, wired together here as one reusable call so the CLI (and anyone
else) doesn't have to re-derive it.
"""

from __future__ import annotations

from pathlib import Path

from .adapters.maskflow_adapter import MaskflowAdapter
from .labels import canonical_labels, identity_map
from .loader import load_my_data
from .runner import AdapterRunResult, run_adapter


def score_my_data(
    path: Path, limit: int | None = None
) -> tuple[int, tuple[str, ...], AdapterRunResult]:
    """Returns (num_docs, canonical_labels, result). Raises LoaderError
    (loader.py) on a malformed line, FileNotFoundError if `path` doesn't
    exist."""
    docs = load_my_data(path, limit=limit)
    labels = canonical_labels(docs)
    entry = (MaskflowAdapter(), identity_map(labels))
    result = run_adapter(entry, docs, labels)
    return len(docs), labels, result
