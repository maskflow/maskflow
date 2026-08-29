"""Puts the repo root on sys.path so `from bench.indiapii.quality... import
...` resolves -- bench/ and bench/indiapii/ are namespace packages (no
__init__.py), so they need the repo root importable, which pytest doesn't
do automatically for a package whose own tests/ directory has no
__init__.py. Mirrors bench/indiapii/harness/tests/conftest.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
