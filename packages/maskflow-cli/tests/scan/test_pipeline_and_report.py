from __future__ import annotations

import json
import tracemalloc
from pathlib import Path

import pytest
from maskflow_cli.app import app
from maskflow_cli.scan.checkpoint import CheckpointMismatch, load_checkpoint
from maskflow_cli.scan.pipeline import PipelineConfig, run_pipeline
from maskflow_cli.scan.report import build_summary, render
from maskflow_cli.scan.sources import get_source
from maskflow_cli.scan.spec import SourceSpec
from maskflow_core.config.resolve import resolve_config
from typer.testing import CliRunner

runner = CliRunner()


def _corpus(path: Path, n: int) -> None:
    lines = []
    for i in range(n):
        lines.append(
            json.dumps(
                {
                    "messages": [{"content": f"Email user{i}@example.com about invoice {i}."}],
                    "model": "gpt-4o",
                    "ts": "2026-05-01T10:00:00",
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cfg(**kw) -> PipelineConfig:
    root = resolve_config().config
    kw.setdefault("workers", 1)
    return PipelineConfig(root_config=root, ner_available=False, **kw)


def test_pipeline_counts(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    _corpus(p, 50)
    src = get_source(SourceSpec(kind="jsonl", target=str(p), fields=("messages[].content",)))
    result = run_pipeline(src, _cfg())
    assert result.aggregator.records_processed == 50
    assert result.aggregator.by_entity_measured["EMAIL"] == 50


def test_pool_path_matches_inline(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    _corpus(p, 700)  # > _CHUNK so more than one batch per worker
    spec = SourceSpec(kind="jsonl", target=str(p), fields=("messages[].content",))
    inline = run_pipeline(get_source(spec), _cfg(workers=1))
    pooled = run_pipeline(get_source(spec), _cfg(workers=3))
    assert pooled.aggregator.records_processed == inline.aggregator.records_processed == 700
    assert pooled.aggregator.by_entity_measured == inline.aggregator.by_entity_measured
    assert pooled.aggregator.distinct_count("EMAIL") == inline.aggregator.distinct_count("EMAIL")


def test_pool_path_sample_cap(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    _corpus(p, 2000)
    spec = SourceSpec(kind="jsonl", target=str(p), fields=("messages[].content",))
    result = run_pipeline(get_source(spec), _cfg(workers=3, max_records=250))
    assert result.stopped_early
    assert result.aggregator.records_processed == 250


def test_sample_cap_stops_early(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    _corpus(p, 100)
    src = get_source(SourceSpec(kind="jsonl", target=str(p), fields=("messages[].content",)))
    result = run_pipeline(src, _cfg(max_records=20))
    assert result.stopped_early
    assert result.aggregator.records_processed == 20


def test_checkpoint_resume_matches_uninterrupted(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    _corpus(p, 60)
    spec = SourceSpec(kind="jsonl", target=str(p), fields=("messages[].content",))
    fp = spec.fingerprint()

    ck = tmp_path / "ck.json"
    run_pipeline(
        get_source(spec),
        _cfg(max_records=25, checkpoint_path=ck, checkpoint_every=1, spec_fingerprint=fp),
    )
    assert load_checkpoint(ck, spec_fingerprint=fp, detection_fingerprint="") is not None

    resumed = run_pipeline(
        get_source(spec),
        _cfg(checkpoint_path=ck, checkpoint_every=1, spec_fingerprint=fp),
    )
    assert resumed.resumed
    assert resumed.aggregator.records_processed == 60
    assert resumed.aggregator.by_entity_measured["EMAIL"] == 60


def test_checkpoint_mismatch_refuses(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    _corpus(p, 10)
    spec = SourceSpec(kind="jsonl", target=str(p), fields=("messages[].content",))
    ck = tmp_path / "ck.json"
    run_pipeline(
        get_source(spec),
        _cfg(
            checkpoint_path=ck,
            checkpoint_every=1,
            spec_fingerprint="AAAA",
            detection_fingerprint="X",
        ),
    )
    with pytest.raises(CheckpointMismatch):
        run_pipeline(
            get_source(spec),
            _cfg(checkpoint_path=ck, spec_fingerprint="BBBB", detection_fingerprint="X"),
        )


@pytest.mark.benchmark
def test_bounded_memory_over_large_corpus(tmp_path: Path) -> None:
    p = tmp_path / "big.jsonl"
    _corpus(p, 20_000)
    src = get_source(SourceSpec(kind="jsonl", target=str(p), fields=("messages[].content",)))
    tracemalloc.start()
    run_pipeline(src, _cfg(distinct_cap=1_000))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # 20k records but distinct_cap=1000 and reservoir excerpts -- peak must
    # stay well under what holding every finding would need.
    assert peak < 80 * 1024 * 1024, f"peak {peak / 1e6:.1f} MB"


def test_report_html_structure(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    _corpus(p, 30)
    src = get_source(SourceSpec(kind="jsonl", target=str(p), fields=("messages[].content",)))
    result = run_pipeline(src, _cfg())
    from datetime import datetime

    summary = build_summary(
        result.aggregator,
        source_kind="jsonl",
        source_target=str(p),
        deep=False,
        ner_available=False,
        generated_at=datetime(2026, 5, 2, 12),
        detector_versions={"maskflow-core": "9.9.9"},
        corpus_fingerprint="abc123",
        thresholds_note="defaults",
    )
    html = render(summary, "html")
    assert "<!doctype html>" in html
    assert "Runs entirely locally. Nothing is transmitted." in html
    assert "DPDP Rule 6" in html
    assert "<!-- DPDP_RULE6_APPENDIX -->" in html
    assert "No raw PII value appears anywhere" in html
    # zero external references
    for needle in ("http://", "https://fonts", "cdn.", "<script src", "<link "):
        assert needle not in html
    assert "30" in html  # records examined


def test_cli_end_to_end(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    _corpus(p, 15)
    out = tmp_path / "r.json"
    result = runner.invoke(
        app,
        [
            "scan",
            "jsonl",
            str(p),
            "--field",
            "messages[].content",
            "--format",
            "json",
            "--out",
            str(out),
            "--workers",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert data["headline_total"] == 15
