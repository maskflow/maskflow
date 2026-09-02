from __future__ import annotations

import json
from pathlib import Path

import pytest
from maskflow_cli.scan.sources import get_source
from maskflow_cli.scan.sources.base import SourceConfigError
from maskflow_cli.scan.spec import SourceSpec


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_jsonl_extracts_and_attributes(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _jsonl(
        p,
        [
            {"messages": [{"content": "one"}, {"content": "two"}], "model": "gpt-4o"},
            {"messages": [{"content": "three"}], "model": "claude"},
        ],
    )
    spec = SourceSpec(
        kind="jsonl",
        target=str(p),
        fields=("messages[].content",),
        service_field="model",
        provider="openai",
    )
    src = get_source(spec)
    assert src.preflight().ok
    recs = list(src.records())
    assert [r.text for r in recs] == ["one", "two", "three"]
    assert {r.service for r in recs} == {"gpt-4o", "claude"}
    assert all(r.provider == "openai" for r in recs)
    # ids unique
    assert len({r.id for r in recs}) == 3


def test_jsonl_resume_skips_processed_prefix(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _jsonl(p, [{"c": f"line{i}"} for i in range(10)])
    spec = SourceSpec(kind="jsonl", target=str(p), fields=("c",))
    src = get_source(spec)
    recs = list(src.records())
    cursor = src.cursor_after(recs[3])
    resumed = list(src.records(resume_cursor=cursor))
    assert [r.text for r in resumed] == [f"line{i}" for i in range(4, 10)]


def test_jsonl_skips_invalid_lines(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text('{"c": "ok"}\nnot json\n{"c": "ok2"}\n', encoding="utf-8")
    spec = SourceSpec(kind="jsonl", target=str(p), fields=("c",))
    assert [r.text for r in get_source(spec).records()] == ["ok", "ok2"]


def test_jsonl_requires_field(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _jsonl(p, [{"c": "x"}])
    with pytest.raises(SourceConfigError):
        get_source(SourceSpec(kind="jsonl", target=str(p)))


def test_csv_source(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("prompt,completion,model\nhello,world,gpt-4o\nfoo,bar,claude\n", encoding="utf-8")
    spec = SourceSpec(
        kind="csv",
        target=str(p),
        columns=("prompt,completion",),
        service_field="model",
    )
    src = get_source(spec)
    assert src.preflight().ok
    recs = list(src.records())
    assert sorted(r.text for r in recs) == ["bar", "foo", "hello", "world"]
    assert {r.service for r in recs} == {"gpt-4o", "claude"}


def test_csv_resume_by_row(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("c\n" + "\n".join(f"v{i}" for i in range(6)) + "\n", encoding="utf-8")
    spec = SourceSpec(kind="csv", target=str(p), columns=("c",))
    src = get_source(spec)
    recs = list(src.records())
    resumed = list(src.records(resume_cursor=src.cursor_after(recs[2])))
    assert [r.text for r in resumed] == ["v3", "v4", "v5"]


def test_dir_source_mixed_files(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_text('{"c": "json-text"}\n', encoding="utf-8")
    (tmp_path / "b.txt").write_text("plain line one\nplain line two\n", encoding="utf-8")
    (tmp_path / "c.csv").write_text("col\ncsv-text\n", encoding="utf-8")
    spec = SourceSpec(kind="dir", target=str(tmp_path), fields=("c",), columns=("col",))
    src = get_source(spec)
    assert src.preflight().ok
    texts = sorted(r.text for r in src.records())
    assert texts == ["csv-text", "json-text", "plain line one", "plain line two"]


def test_missing_file_preflight(tmp_path: Path) -> None:
    with pytest.raises(SourceConfigError):
        get_source(SourceSpec(kind="jsonl", target=str(tmp_path / "nope.jsonl"), fields=("c",)))
