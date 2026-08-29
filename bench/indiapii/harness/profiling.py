"""Latency (ms/KB) and peak-memory (RSS delta) measurement for one
adapter's run over a corpus.

Known limitation (documented, not hidden): adapters run in-process,
sequentially, not subprocess-isolated -- ru_maxrss is a whole-process,
monotonically-nondecreasing high-water mark, so peak_memory_mb here is an
*attributable delta* across one adapter's calls, not a hard ceiling that
adapter alone ever touched. Good enough for a first cut / relative
comparison, not a substitute for real per-process isolation.
"""

from __future__ import annotations

import resource
import sys
from dataclasses import dataclass, field


def _current_maxrss_mb() -> float:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports ru_maxrss in bytes; Linux reports it in KB.
    return raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024


@dataclass
class ProfileResult:
    latency_ms_per_kb: float
    median_doc_ms: float
    p95_doc_ms: float
    peak_memory_mb: float
    errors: int = 0


@dataclass
class Profiler:
    _doc_ms: list[float] = field(default_factory=list)
    _total_bytes: int = 0
    _start_rss_mb: float = 0.0
    _started: bool = False
    errors: int = 0

    def start(self) -> None:
        self._start_rss_mb = _current_maxrss_mb()
        self._started = True

    def record(self, elapsed_seconds: float, size_bytes: int) -> None:
        self._doc_ms.append(elapsed_seconds * 1000)
        self._total_bytes += size_bytes

    def finish(self) -> ProfileResult:
        end_rss_mb = _current_maxrss_mb()
        total_ms = sum(self._doc_ms)
        total_kb = (self._total_bytes / 1024) or 1.0
        sorted_ms = sorted(self._doc_ms)
        median = sorted_ms[len(sorted_ms) // 2] if sorted_ms else 0.0
        p95_idx = min(len(sorted_ms) - 1, int(len(sorted_ms) * 0.95)) if sorted_ms else 0
        p95 = sorted_ms[p95_idx] if sorted_ms else 0.0
        start_rss = self._start_rss_mb if self._started else end_rss_mb
        return ProfileResult(
            latency_ms_per_kb=total_ms / total_kb,
            median_doc_ms=median,
            p95_doc_ms=p95,
            peak_memory_mb=max(0.0, end_rss_mb - start_rss),
            errors=self.errors,
        )
