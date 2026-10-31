"""bench/ directories are namespace packages, not installed ones, so the
repository root has to be on sys.path for `bench.auditbench` to import.
Same shim as bench/tabular/tests/conftest.py."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
