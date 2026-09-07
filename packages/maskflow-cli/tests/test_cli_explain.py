from __future__ import annotations

from pathlib import Path

from maskflow_cli.app import app
from typer.testing import CliRunner

runner = CliRunner()


def test_explain_masks_a_detected_email_and_truncates_the_match() -> None:
    result = runner.invoke(app, ["explain", "Email me at john.doe@example.com please"])
    assert result.exit_code == 0
    assert "EMAIL" in result.stdout
    assert "masked" in result.stdout
    # Truncated to 8 chars + an ellipsis by default -- the full address
    # (>8 chars) must never appear verbatim.
    assert "john.doe@example.com" not in result.stdout
    assert "john.doe" in result.stdout


def test_explain_full_flag_shows_the_entire_match() -> None:
    result = runner.invoke(app, ["explain", "--full", "Email me at john.doe@example.com please"])
    assert result.exit_code == 0
    assert "john.doe@example.com" in result.stdout


def test_explain_reports_a_near_miss_with_a_maskflowrc_snippet() -> None:
    result = runner.invoke(
        app, ["explain", "Random unrelated text with a number 123456789 in it, nothing special."]
    )
    assert result.exit_code == 0
    assert "NEAREST MISSES" in result.stdout
    assert "[entities.SSN]" in result.stdout
    assert "threshold = 0.35" in result.stdout
    # The bare 9-digit run itself (>8 chars) must still be truncated here too.
    assert "123456789" not in result.stdout


def test_explain_no_pii_detected() -> None:
    result = runner.invoke(app, ["explain", "nothing interesting here at all"])
    assert result.exit_code == 0
    assert "No PII detected" in result.stdout


def test_explain_set_override_disables_an_entity() -> None:
    result = runner.invoke(
        app, ["explain", "--set", "entities.EMAIL.enabled=false", "Email me at a@b.com"]
    )
    assert result.exit_code == 0
    assert "EMAIL" not in result.stdout


def test_explain_lowering_threshold_via_set_promotes_a_near_miss_to_masked() -> None:
    text = "Random unrelated text with a number 123456789 in it, nothing special."
    result = runner.invoke(app, ["explain", "--set", "entities.SSN.threshold=0.3", text])
    assert result.exit_code == 0
    assert "masked" in result.stdout
    # SSN itself moved out of the near-miss section and into the masked
    # section above it -- maskflow-pack-india's BANK_ACCOUNT_IN (9-18
    # digits, always context-required) is a separate, still-legitimate
    # near miss on this same bare 9-digit span, so "no near misses at all"
    # isn't the right assertion here.
    assert "[1] SSN" in result.stdout
    assert "[entities.SSN]" not in result.stdout


def test_explain_bad_config_exits_nonzero(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["explain", "--config", str(fixtures_dir / "typo.toml"), "hello"])
    assert result.exit_code == 1
    assert "did you mean 'threshold'?" in result.stderr


# --- --evidence -------------------------------------------------------


def test_explain_evidence_file_writes_metadata_only(tmp_path: Path) -> None:
    import json

    out = tmp_path / "evidence.log"
    result = runner.invoke(
        app,
        ["explain", "--evidence-file", str(out), "Email me at john.doe@example.com please"],
    )
    assert result.exit_code == 0
    lines = out.read_text().strip().splitlines()
    assert lines
    record = json.loads(lines[0])
    assert record["entity_type"] == "EMAIL"
    assert record["action"] == "masked"
    assert record["recognizer"] == "pattern:EMAIL"
    # the value itself never appears
    assert "john.doe@example.com" not in out.read_text()


def test_explain_no_evidence_by_default(tmp_path: Path) -> None:
    # no --evidence, no [evidence] config -> nothing written anywhere
    result = runner.invoke(app, ["explain", "Email me at john.doe@example.com please"])
    assert result.exit_code == 0
    assert not (tmp_path / "evidence.log").exists()


def test_explain_evidence_reports_near_misses_as_passed(tmp_path: Path) -> None:
    import json

    out = tmp_path / "e.log"
    text = "Random unrelated text with a number 123456789 in it, nothing special."
    result = runner.invoke(app, ["explain", "--evidence-file", str(out), text])
    assert result.exit_code == 0
    actions = {json.loads(line)["action"] for line in out.read_text().strip().splitlines()}
    assert "passed" in actions
    assert "123456789" not in out.read_text()
