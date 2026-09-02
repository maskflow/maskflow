"""Fold a finished Aggregator into a ScanSummary: apply the NER-sample
extrapolation, attach severity + "why this matters", shape the breakdowns
and the time series."""

from __future__ import annotations

from datetime import datetime

from ..aggregate import Aggregator
from ..severity import classify
from .summary import (
    Breakdown,
    Methodology,
    ScanScope,
    ScanSummary,
    SeverityRow,
    TimeBucket,
)

_TOP_N = 25


def build_summary(
    agg: Aggregator,
    *,
    source_kind: str,
    source_target: str,
    deep: bool,
    ner_available: bool = True,
    generated_at: datetime,
    detector_versions: dict[str, str],
    corpus_fingerprint: str,
    thresholds_note: str,
) -> ScanSummary:
    factor = _extrapolation_factor(agg, deep)
    if deep:
        mode = "deep (full pipeline)"
    elif ner_available:
        mode = "patterns (full corpus) + NER sample"
    else:
        mode = "patterns only (NER pass unavailable)"

    entity_counts: dict[str, tuple[int, bool]] = {}  # et -> (count, estimated)
    for et in sorted(agg.entity_types()):
        measured = agg.by_entity_measured.get(et, 0)
        sampled = agg.by_entity_sampled.get(et, 0)
        estimated_part = round(sampled * factor)
        total = measured + estimated_part
        if total:
            entity_counts[et] = (total, sampled > 0 and factor != 1.0)

    headline_total = sum(c for c, _ in entity_counts.values())
    headline_has_estimate = any(est for _, est in entity_counts.values())

    by_entity_type = tuple(
        Breakdown(
            label=et,
            count=count,
            distinct=agg.distinct_count(et)[0],
            distinct_is_lower_bound=agg.distinct_count(et)[1],
            estimated=estimated,
            severity=classify(et)[0].label,
        )
        for et, (count, estimated) in sorted(
            entity_counts.items(), key=lambda kv: (-kv[1][0], kv[0])
        )
    )
    headline_distinct = sum(b.distinct or 0 for b in by_entity_type)

    severity_rows = tuple(
        sorted(
            (
                _severity_row(agg, et, count, estimated)
                for et, (count, estimated) in entity_counts.items()
            ),
            key=lambda r: (-r.severity_rank, -r.count),
        )
    )

    scope = ScanScope(
        source_kind=source_kind,
        source_target=source_target,
        records_processed=agg.records_processed,
        records_with_pii=agg.records_with_findings,
        detection_mode=mode,
        ner_sample_records=agg.ner_sample_records,
        extrapolation_factor=factor,
        date_range=_date_range(agg),
        generated_at=generated_at,
    )

    return ScanSummary(
        scope=scope,
        headline_total=headline_total,
        headline_distinct=headline_distinct,
        headline_has_estimate=headline_has_estimate,
        providers=tuple(sorted(agg.by_provider)),
        by_entity_type=by_entity_type,
        by_provider=_counter_breakdown(agg.by_provider),
        by_service=_counter_breakdown(agg.by_service),
        time_series=_time_series(agg),
        time_bucket_unit="day",
        severity_rows=severity_rows,
        methodology=Methodology(
            detector_versions=detector_versions,
            entity_types_scanned=tuple(sorted(agg.entity_types())),
            thresholds_note=thresholds_note,
            not_scanned_note=_not_scanned_note(deep, ner_available),
            corpus_fingerprint=corpus_fingerprint,
        ),
    )


def _extrapolation_factor(agg: Aggregator, deep: bool) -> float:
    if deep:
        return 1.0
    if agg.ner_sample_records == 0 or agg.ner_sample_records >= agg.records_processed:
        return 1.0
    return agg.records_processed / agg.ner_sample_records


def _severity_row(agg: Aggregator, et: str, count: int, estimated: bool) -> SeverityRow:
    sev, why = classify(et)
    distinct, lower_bound = agg.distinct_count(et)
    return SeverityRow(
        entity_type=et,
        severity=sev.label,
        severity_rank=int(sev),
        count=count,
        distinct=distinct,
        distinct_is_lower_bound=lower_bound,
        providers=tuple(agg.providers_for(et)),
        why_it_matters=why,
        excerpts=tuple(agg.excerpts(et)),
        estimated=estimated,
    )


def _counter_breakdown(counter: dict[str, int]) -> tuple[Breakdown, ...]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    top = items[:_TOP_N]
    rows = [Breakdown(label=label, count=count) for label, count in top]
    rest = sum(count for _, count in items[_TOP_N:])
    if rest:
        rows.append(Breakdown(label=f"other ({len(items) - _TOP_N} more)", count=rest))
    return tuple(rows)


def _time_series(agg: Aggregator) -> tuple[TimeBucket, ...]:
    if not agg.by_day:
        return ()
    return tuple(TimeBucket(start=day, count=count) for day, count in sorted(agg.by_day.items()))


def _date_range(agg: Aggregator) -> tuple[datetime, datetime] | None:
    if agg.min_ts is None or agg.max_ts is None:
        return None
    return datetime.fromisoformat(agg.min_ts), datetime.fromisoformat(agg.max_ts)


def _not_scanned_note(deep: bool, ner_available: bool) -> str:
    tail = (
        " Binary attachments, images, and audio were not scanned; only text "
        "fields selected by the source configuration were examined."
    )
    if deep:
        return "Every record ran through the full detection pipeline." + tail
    if not ner_available:
        return (
            "The NER pass (bare personal names and postal addresses) was "
            "unavailable in this environment, so those types are absent from "
            "this report. Pattern- and checksum-based identifiers are complete." + tail
        )
    return (
        "Bare personal names and postal addresses (NER-detected) were measured "
        "on a sample and extrapolated, not counted exhaustively -- run with "
        "--deep for exact figures." + tail
    )
