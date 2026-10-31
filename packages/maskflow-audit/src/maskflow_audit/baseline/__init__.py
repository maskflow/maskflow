"""The CI gate: a committed baseline, and a diff against it."""

from __future__ import annotations

from .diff import (
    BASELINE_FILENAME,
    BASELINE_SCHEMA_VERSION,
    Baseline,
    BaselineError,
    CiVerdict,
    build_baseline,
    diff_against,
    load_baseline,
    write_baseline,
)

__all__ = [
    "BASELINE_FILENAME",
    "BASELINE_SCHEMA_VERSION",
    "Baseline",
    "BaselineError",
    "CiVerdict",
    "build_baseline",
    "diff_against",
    "load_baseline",
    "write_baseline",
]
