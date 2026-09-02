"""The streaming Aggregator: fold a stream of FindingSeeds into fixed-size
summary state, so peak memory is O(entity_types x caps) regardless of
corpus size.

Everything it holds is PII-free -- counters, HMAC fingerprints, and
already-masked excerpts -- so `to_state()` can be written straight into the
checkpoint file (same guarantee as the report).
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from .worker import FindingSeed

DEFAULT_DISTINCT_CAP = 50_000
DEFAULT_EXCERPT_CAP = 20


@dataclass
class Aggregator:
    distinct_cap: int = DEFAULT_DISTINCT_CAP
    excerpt_cap: int = DEFAULT_EXCERPT_CAP
    # Fixed seed: excerpt reservoir sampling is deterministic run-to-run,
    # so a resumed scan and an uninterrupted one pick the same examples.
    _rng: random.Random = field(default_factory=lambda: random.Random(1_234_567))

    records_processed: int = 0
    records_with_findings: int = 0

    # Full-coverage counts (pattern pass + --deep). Extrapolation never
    # applies to these.
    total_measured: int = 0
    by_entity_measured: Counter[str] = field(default_factory=Counter)
    # Counts seen only in the NER sample (not --deep) -- extrapolated later.
    by_entity_sampled: Counter[str] = field(default_factory=Counter)
    ner_sample_records: int = 0

    by_provider: Counter[str] = field(default_factory=Counter)
    by_service: Counter[str] = field(default_factory=Counter)
    by_day: Counter[str] = field(default_factory=Counter)
    entity_provider: Counter[str] = field(default_factory=Counter)  # "ENTITY\x1fprovider"

    _distinct: dict[str, set[str]] = field(default_factory=dict)
    distinct_overflow: set[str] = field(default_factory=set)

    _excerpts: dict[str, list[str]] = field(default_factory=dict)
    _excerpt_seen: Counter[str] = field(default_factory=Counter)

    min_ts: str | None = None
    max_ts: str | None = None

    def add(
        self,
        seeds: list[FindingSeed],
        *,
        provider: str | None,
        service: str | None,
        timestamp: datetime | None,
        in_ner_sample: bool,
    ) -> None:
        self.records_processed += 1
        if in_ner_sample:
            self.ner_sample_records += 1
        if seeds:
            self.records_with_findings += 1

        day = timestamp.date().isoformat() if timestamp else None
        if timestamp:
            iso = timestamp.isoformat()
            self.min_ts = iso if self.min_ts is None or iso < self.min_ts else self.min_ts
            self.max_ts = iso if self.max_ts is None or iso > self.max_ts else self.max_ts

        for seed in seeds:
            et = seed.entity_type
            if seed.from_ner:
                self.by_entity_sampled[et] += 1
            else:
                self.total_measured += 1
                self.by_entity_measured[et] += 1

            if provider:
                self.by_provider[provider] += 1
                self.entity_provider[f"{et}\x1f{provider}"] += 1
            if service:
                self.by_service[service] += 1
            if day:
                self.by_day[day] += 1

            self._add_distinct(et, seed.value_fingerprint)
            self._add_excerpt(et, seed.masked_excerpt)

    def _add_distinct(self, entity_type: str, fingerprint: str) -> None:
        bucket = self._distinct.setdefault(entity_type, set())
        if len(bucket) >= self.distinct_cap:
            self.distinct_overflow.add(entity_type)
            return
        bucket.add(fingerprint)

    def _add_excerpt(self, entity_type: str, excerpt: str) -> None:
        if not excerpt:
            return
        self._excerpt_seen[entity_type] += 1
        n = self._excerpt_seen[entity_type]
        pool = self._excerpts.setdefault(entity_type, [])
        if len(pool) < self.excerpt_cap:
            pool.append(excerpt)
        else:
            j = self._rng.randint(0, n - 1)
            if j < self.excerpt_cap:
                pool[j] = excerpt

    # -- read views -------------------------------------------------------

    def distinct_count(self, entity_type: str) -> tuple[int, bool]:
        """(count, is_lower_bound). is_lower_bound True once the cap was hit."""
        n = len(self._distinct.get(entity_type, ()))
        return n, entity_type in self.distinct_overflow

    def excerpts(self, entity_type: str) -> list[str]:
        return list(self._excerpts.get(entity_type, ()))

    def entity_types(self) -> set[str]:
        return set(self.by_entity_measured) | set(self.by_entity_sampled)

    def providers_for(self, entity_type: str) -> list[str]:
        out = []
        for key, count in self.entity_provider.items():
            et, provider = key.split("\x1f", 1)
            if et == entity_type and count:
                out.append(provider)
        return sorted(out)

    # -- checkpoint (de)serialisation -----------------------------------

    def to_state(self) -> dict:
        return {
            "records_processed": self.records_processed,
            "records_with_findings": self.records_with_findings,
            "total_measured": self.total_measured,
            "by_entity_measured": dict(self.by_entity_measured),
            "by_entity_sampled": dict(self.by_entity_sampled),
            "ner_sample_records": self.ner_sample_records,
            "by_provider": dict(self.by_provider),
            "by_service": dict(self.by_service),
            "by_day": dict(self.by_day),
            "entity_provider": dict(self.entity_provider),
            "distinct": {k: sorted(v) for k, v in self._distinct.items()},
            "distinct_overflow": sorted(self.distinct_overflow),
            "excerpts": {k: list(v) for k, v in self._excerpts.items()},
            "excerpt_seen": dict(self._excerpt_seen),
            "min_ts": self.min_ts,
            "max_ts": self.max_ts,
        }

    @classmethod
    def from_state(cls, state: dict, *, distinct_cap: int, excerpt_cap: int) -> Aggregator:
        agg = cls(distinct_cap=distinct_cap, excerpt_cap=excerpt_cap)
        agg.records_processed = state["records_processed"]
        agg.records_with_findings = state["records_with_findings"]
        agg.total_measured = state["total_measured"]
        agg.by_entity_measured = Counter(state["by_entity_measured"])
        agg.by_entity_sampled = Counter(state["by_entity_sampled"])
        agg.ner_sample_records = state["ner_sample_records"]
        agg.by_provider = Counter(state["by_provider"])
        agg.by_service = Counter(state["by_service"])
        agg.by_day = Counter(state["by_day"])
        agg.entity_provider = Counter(state["entity_provider"])
        agg._distinct = {k: set(v) for k, v in state["distinct"].items()}
        agg.distinct_overflow = set(state["distinct_overflow"])
        agg._excerpts = {k: list(v) for k, v in state["excerpts"].items()}
        agg._excerpt_seen = Counter(state["excerpt_seen"])
        agg.min_ts = state["min_ts"]
        agg.max_ts = state["max_ts"]
        return agg
