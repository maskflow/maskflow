"""Guards the intl-pii-v1.0 generator: the committed corpus must be exactly
what today's generator code produces from the recorded seed, and every
checksum-bearing value in it must still pass maskflow-pack-intl's own
validators. Not marked `benchmark` -- it is a cheap correctness check with
no third-party adapter deps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_GEN_DIR = Path(__file__).resolve().parents[2] / "generator"
sys.path.insert(0, str(_GEN_DIR.parent))

from generator.generate import VERSION, generate_corpus, self_check  # noqa: E402

_CORPUS = Path(__file__).resolve().parents[2] / "data" / "intl-pii-v1.0.jsonl"
_SEED = 20260910
_COUNT = 1800


def _committed() -> list[dict]:
    with _CORPUS.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_committed_corpus_is_reproducible_from_seed() -> None:
    fresh = generate_corpus(_COUNT, _SEED)
    committed = _committed()
    assert len(committed) == _COUNT
    assert committed == fresh, "committed corpus drifted from the generator -- regenerate it"


def test_committed_corpus_passes_self_check() -> None:
    checked, failed, failures = self_check(_committed())
    assert checked > 0
    assert failed == 0, failures[:10]


def test_corpus_version_tag_matches() -> None:
    assert VERSION == "intl-pii-v1.0"
    assert all(d["id"].startswith(VERSION) for d in _committed())
