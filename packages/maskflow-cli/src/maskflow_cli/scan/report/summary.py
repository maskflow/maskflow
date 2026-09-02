"""The PII-free report data model. `html.py`, `json_out.py`, and `csv_out.py`
all render from a `ScanSummary` and nothing else -- so "does the report leak
PII?" reduces to "is every string on this object PII-free?", which the fuzz
gate checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ScanScope:
    source_kind: str
    source_target: str  # a path / uri / "langfuse" -- never credentials
    records_processed: int
    records_with_pii: int
    detection_mode: str  # "patterns + NER sample" | "deep (full pipeline)"
    ner_sample_records: int
    extrapolation_factor: float  # 1.0 when deep or fully sampled
    date_range: tuple[datetime, datetime] | None
    generated_at: datetime


@dataclass(frozen=True)
class Breakdown:
    label: str
    count: int
    distinct: int | None = None
    distinct_is_lower_bound: bool = False
    estimated: bool = False
    severity: str | None = None


@dataclass(frozen=True)
class TimeBucket:
    start: str  # ISO date or hour
    count: int


@dataclass(frozen=True)
class SeverityRow:
    entity_type: str
    severity: str  # "Critical" | "High" | "Medium" | "Low"
    severity_rank: int
    count: int
    distinct: int
    distinct_is_lower_bound: bool
    providers: tuple[str, ...]
    why_it_matters: str
    excerpts: tuple[str, ...]
    estimated: bool


@dataclass(frozen=True)
class Methodology:
    detector_versions: dict[str, str]
    entity_types_scanned: tuple[str, ...]
    thresholds_note: str
    not_scanned_note: str
    corpus_fingerprint: str


@dataclass(frozen=True)
class ScanSummary:
    scope: ScanScope
    headline_total: int
    headline_distinct: int
    headline_has_estimate: bool
    providers: tuple[str, ...]
    by_entity_type: tuple[Breakdown, ...]
    by_provider: tuple[Breakdown, ...]
    by_service: tuple[Breakdown, ...]
    time_series: tuple[TimeBucket, ...]
    time_bucket_unit: str  # "day" | "hour"
    severity_rows: tuple[SeverityRow, ...]
    methodology: Methodology
    dpdp_appendix_slot: str = field(default="<!-- DPDP_RULE6_APPENDIX -->")
