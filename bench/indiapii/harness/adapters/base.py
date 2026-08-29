"""The Adapter protocol every competitor detector implements.

`available()` is checked once per harness run, before any `detect()` call:
an adapter missing an optional dependency (presidio, mask-privacy) or an
API key (the LLM adapter) reports `(False, reason)` and is skipped, never
crashing the run. `detect()` itself is called once per document by
runner.py, which wraps each call in its own bounded try/except so one bad
document can't take out the rest of an adapter's run either.
"""

from __future__ import annotations

from typing import Protocol


class Adapter(Protocol):
    name: str

    def available(self) -> tuple[bool, str]:
        """Returns (True, "") if this adapter can run, else (False, reason)."""
        ...

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        """Returns (start, end, raw_label) spans in this adapter's own
        label vocabulary -- translated to the corpus's canonical labels by
        labels.py, not here."""
        ...
