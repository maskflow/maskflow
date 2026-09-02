"""Guards the shipped example so it can't silently rot: it must stay valid
JSONL and stay scannable with the flags the README documents."""

from __future__ import annotations

import json
from pathlib import Path

from maskflow_cli.app import app
from typer.testing import CliRunner

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "sample-llm-traffic.jsonl"
runner = CliRunner()


def test_example_is_valid_jsonl() -> None:
    lines = _EXAMPLE.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 60
    for line in lines:
        row = json.loads(line)
        assert isinstance(row["messages"][0]["content"], str)
        assert row["provider"] in {"openai", "anthropic", "google"}


def test_readme_command_scans_the_example(tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    result = runner.invoke(
        app,
        [
            "scan",
            "jsonl",
            str(_EXAMPLE),
            "--field",
            "messages[].content",
            "--provider-field",
            "provider",
            "--service-field",
            "model",
            "--timestamp-field",
            "created_at",
            "--deep",
            "--out",
            str(out),
            "--quiet",
        ],
    )
    assert result.exit_code == 0, result.output
    html = out.read_text(encoding="utf-8")
    assert "PII Exposure Scan" in html
    assert "AADHAAR" in html
    # the README claims a realistic ratio -- keep it honest
    import re

    m = re.search(r"(\d+) records examined", html)
    assert m and int(m.group(1)) == 60


def test_patterns_only_report_has_no_raw_dob(tmp_path: Path) -> None:
    """The sample's KYC prompts put a bare DOB next to Aadhaar/PAN.
    DATE_OF_BIRTH is NER-only, so a patterns-only run (no --deep) must still
    not surface a raw birth-date in an excerpt -- the excerpt date scrub
    covers that."""
    out = tmp_path / "report.html"
    result = runner.invoke(
        app,
        [
            "scan",
            "jsonl",
            str(_EXAMPLE),
            "--field",
            "messages[].content",
            "--out",
            str(out),
            "--quiet",
        ],
    )
    assert result.exit_code == 0, result.output
    import re

    html = out.read_text(encoding="utf-8")
    # The sample's birth-years are all 19xx; the report's own dates (scan
    # range, time-series buckets) are 20xx, so a 19xx date would be a
    # leaked DOB.
    assert not re.search(r"\b19\d\d-\d\d-\d\d\b", html)
    # And every rendered excerpt shows dates only as the <DATE> placeholder.
    for excerpt in re.findall(r'<div class="excerpt">(.*?)</div>', html, re.S):
        assert not re.search(r"\d{4}-\d{2}-\d{2}", excerpt)
