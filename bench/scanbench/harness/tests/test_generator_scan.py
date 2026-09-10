"""Guards the scan-log-v1.0 generator: the committed corpus must be exactly
what today's generator produces from the recorded seed, and every
checksum-bearing gold value must still pass the packs' validators.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_GEN = Path(__file__).resolve().parents[2] / "generator"
sys.path.insert(0, str(_GEN.parents[2]))  # repo root

from bench.scanbench.generator.generate import (  # noqa: E402
    VERSION,
    generate_corpus,
    self_check,
)

_CORPUS = Path(__file__).resolve().parents[2] / "data" / "scan-log-v1.0.jsonl"
_SEED = 20260910
_COUNT = 2000


def _committed() -> list[dict]:
    with _CORPUS.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_committed_corpus_reproducible_from_seed() -> None:
    committed = _committed()
    assert len(committed) == _COUNT
    assert committed == generate_corpus(_COUNT, _SEED), "corpus drifted -- regenerate it"


def test_committed_corpus_passes_self_check() -> None:
    checked, failed, failures = self_check(_committed())
    assert checked > 0
    assert failed == 0, failures[:10]


def test_version_tag() -> None:
    assert VERSION == "scan-log-v1.0"
    assert all(d["id"].startswith(VERSION) for d in _committed())
