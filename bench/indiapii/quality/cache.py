"""Flat-file disk cache for LLM calls (task-model generations and judge
verdicts): each entry is one JSON file under `cache_dir`, named by the
sha256 of its cache key -- a rerun of `run` that hits every key already
cached makes zero API calls. No eviction or TTL: a benchmark run's cache is
meant to be kept (and inspected), not treated as ephemeral.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, key: str, value: Any) -> None:
        self._path(key).write_text(json.dumps(value), encoding="utf-8")
