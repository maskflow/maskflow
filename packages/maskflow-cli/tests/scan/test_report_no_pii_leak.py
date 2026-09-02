"""The fuzz gate: generate a corpus with known synthetic PII, run the whole
scan pipeline, render every output format, and assert NO injected raw value
survives anywhere in the rendered bytes. Permanent CI job (see ci.yml).
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from maskflow_cli.scan.cmd import scan
from typer import Typer
from typer.testing import CliRunner

from ._fuzz_corpus import build_corpus

runner = CliRunner()
_app = Typer()
_app.command()(scan)


def _normalisations(value: str) -> set[str]:
    forms = {value, value.casefold(), value.replace(" ", ""), value.replace("-", "")}
    for form in ("NFC", "NFKC", "NFKD"):
        forms.add(unicodedata.normalize(form, value))
    return {f for f in forms if f}


def _run(tmp_path: Path, corpus: Path, fmt: str, *extra: str) -> str:
    out = tmp_path / f"report.{fmt}"
    result = runner.invoke(
        _app,
        [
            "jsonl",
            str(corpus),
            "--field",
            "messages[].content",
            "--provider-field",
            "provider",
            "--service-field",
            "model",
            "--timestamp-field",
            "ts",
            "--format",
            fmt,
            "--out",
            str(out),
            "--workers",
            "1",
            *extra,
        ],
    )
    assert result.exit_code == 0, result.output
    return out.read_text(encoding="utf-8")


@pytest.mark.leak
@pytest.mark.parametrize("fmt", ["html", "json", "csv"])
def test_no_injected_pii_survives_in_any_format(tmp_path: Path, fmt: str) -> None:
    corpus = tmp_path / "corpus.jsonl"
    injected = build_corpus(corpus, n=240)

    rendered = _run(tmp_path, corpus, fmt, "--deep")
    haystacks = {rendered, rendered.casefold(), unicodedata.normalize("NFKC", rendered)}

    leaked = [
        value
        for value in injected
        if any(form in hay for form in _normalisations(value) for hay in haystacks)
    ]
    assert not leaked, f"{len(leaked)} raw PII value(s) leaked into {fmt}: {leaked[:5]}"


@pytest.mark.leak
def test_report_is_non_trivial(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    build_corpus(corpus, n=240)
    import json

    data = json.loads(_run(tmp_path, corpus, "json", "--deep"))
    # The corpus plants >=6 detectable identifiers per record over 240
    # records -- the scan must find a substantial number of them, or the
    # "nothing leaked" assertion above is vacuous.
    assert data["headline_total"] > 500
    assert data["scope"]["records_processed"] == 240
    assert any(r["entity_type"] == "AADHAAR" for r in data["severity_rows"])


@pytest.mark.leak
def test_patterns_only_pass_also_leaks_nothing(tmp_path: Path) -> None:
    # The fast path (no --deep) must be just as clean.
    corpus = tmp_path / "corpus.jsonl"
    injected = build_corpus(corpus, n=180)
    rendered = _run(tmp_path, corpus, "html")
    leaked = [v for v in injected if v in rendered]
    assert not leaked, leaked[:5]
