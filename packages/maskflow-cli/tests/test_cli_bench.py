from __future__ import annotations

import json
from pathlib import Path

from maskflow_bench.scorer import score_my_data
from maskflow_cli.app import app
from typer.testing import CliRunner

runner = CliRunner()


def _write_fixture(path: Path) -> None:
    # PAN below is structurally well-formed (5 letters + 4 digits + 1
    # letter) but fabricated for this test, not a real allotted number --
    # synthetic fixture data only, per project policy.
    rows = [
        {
            "id": "fixture-1",
            "text": "Please update my PAN ABCDE1234F on file.",
            "entities": [{"start": 22, "end": 32, "label": "PAN"}],
        },
        {
            "id": "fixture-2",
            "text": "No PII in this line at all.",
            "entities": [],
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_my_data_prints_a_per_entity_table(tmp_path: Path) -> None:
    fixture = tmp_path / "my.jsonl"
    _write_fixture(fixture)

    result = runner.invoke(app, ["bench", "--my-data", str(fixture)])

    assert result.exit_code == 0
    assert "PAN" in result.stdout
    assert "2 document(s)" in result.stdout


def test_my_data_out_writes_results_matching_the_scorer_directly(tmp_path: Path) -> None:
    fixture = tmp_path / "my.jsonl"
    _write_fixture(fixture)
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["bench", "--my-data", str(fixture), "--out", str(out_dir)])

    assert result.exit_code == 0
    data = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    assert (out_dir / "results.md").exists()

    num_docs, labels, expected = score_my_data(fixture)
    assert data["num_docs"] == num_docs
    assert data["canonical_labels"] == list(labels)
    assert data["adapters"]["maskflow"]["available"] is True
    assert data["adapters"]["maskflow"]["strict"]["PAN"]["tp"] == expected.strict["PAN"].tp


def test_my_data_malformed_line_reports_line_number_and_exits_nonzero(tmp_path: Path) -> None:
    fixture = tmp_path / "bad.jsonl"
    fixture.write_text(
        json.dumps({"text": "ok", "entities": []}) + "\n" + json.dumps({"text": "missing ents"}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["bench", "--my-data", str(fixture)])

    assert result.exit_code != 0
    assert "line 2" in result.stdout + result.stderr


def test_my_data_missing_file_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["bench", "--my-data", str(tmp_path / "does-not-exist.jsonl")])
    assert result.exit_code != 0
