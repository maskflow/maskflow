from __future__ import annotations

from datetime import datetime

from maskflow_cli.scan.aggregate import Aggregator
from maskflow_cli.scan.severity import Severity, classify
from maskflow_cli.scan.worker import FindingSeed


def _seed(et: str, fp: str, *, from_ner: bool = False) -> FindingSeed:
    return FindingSeed(et, f"<{et}_1>", fp, f"...<{et}_1>...", from_ner)


def test_counts_and_distinct() -> None:
    agg = Aggregator()
    ts = datetime(2026, 1, 2, 10)
    agg.add(
        [_seed("EMAIL", "fp1"), _seed("EMAIL", "fp1")],
        provider="openai",
        service="gpt-4o",
        timestamp=ts,
        in_ner_sample=False,
    )
    agg.add(
        [_seed("EMAIL", "fp2")],
        provider="anthropic",
        service=None,
        timestamp=ts,
        in_ner_sample=False,
    )
    assert agg.by_entity_measured["EMAIL"] == 3
    count, lower = agg.distinct_count("EMAIL")
    assert count == 2 and lower is False
    assert agg.by_provider == {"openai": 2, "anthropic": 1}
    assert agg.records_processed == 2


def test_distinct_cap_marks_lower_bound() -> None:
    agg = Aggregator(distinct_cap=3)
    for i in range(10):
        agg.add(
            [_seed("PAN", f"fp{i}")],
            provider=None,
            service=None,
            timestamp=None,
            in_ner_sample=False,
        )
    count, lower = agg.distinct_count("PAN")
    assert count == 3 and lower is True


def test_excerpt_reservoir_bounded() -> None:
    agg = Aggregator(excerpt_cap=5)
    for i in range(100):
        agg.add(
            [_seed("AADHAAR", f"fp{i}")],
            provider=None,
            service=None,
            timestamp=None,
            in_ner_sample=False,
        )
    assert len(agg.excerpts("AADHAAR")) == 5


def test_state_round_trip() -> None:
    agg = Aggregator()
    agg.add(
        [_seed("UPI_VPA", "fp1"), _seed("PERSON_NAME", "fpn", from_ner=True)],
        provider="openai",
        service="x",
        timestamp=datetime(2026, 3, 1),
        in_ner_sample=True,
    )
    state = agg.to_state()
    back = Aggregator.from_state(state, distinct_cap=99, excerpt_cap=9)
    assert back.to_state() == state
    assert back.ner_sample_records == 1
    assert back.by_entity_sampled["PERSON_NAME"] == 1


def test_severity_table_covers_known_types() -> None:
    for et in ("AADHAAR", "PAN", "EMAIL", "UPI_VPA", "PERSON_NAME", "IFSC"):
        sev, why = classify(et)
        assert isinstance(sev, Severity)
        assert len(why) > 20
    assert classify("AADHAAR")[0] is Severity.CRITICAL
    assert classify("IFSC")[0] is Severity.LOW


def test_severity_unknown_type_defaults_medium() -> None:
    sev, why = classify("SOME_FUTURE_PACK_TYPE")
    assert sev is Severity.MEDIUM
    assert "DPDP" in why
