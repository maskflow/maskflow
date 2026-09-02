from __future__ import annotations

import sys
from pathlib import Path

# The fuzz-gate corpus builder imports bench.indiapii.generator for
# checksum-valid synthetic identifiers. `bench/` lives at the repo root,
# which isn't on sys.path when only packages/maskflow-cli/tests is
# collected -- add it here.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
