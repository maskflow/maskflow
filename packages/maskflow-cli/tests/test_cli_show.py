from __future__ import annotations

from pathlib import Path

from maskflow_cli.app import app
from typer.testing import CliRunner

runner = CliRunner()


def test_show_plain_toml(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["config", "show", "--config", str(fixtures_dir / "valid.toml")])
    assert result.exit_code == 0
    assert 'default_strategy = "replace"' in result.stdout
    # exclusions.values must never appear verbatim in output.
    assert "test@example.com" not in result.stdout


def test_show_resolved_annotates_provenance(fixtures_dir: Path) -> None:
    result = runner.invoke(
        app, ["config", "show", "--resolved", "--config", str(fixtures_dir / "valid.toml")]
    )
    assert result.exit_code == 0
    assert "entities.AADHAAR.threshold = 0.6" in result.stdout
    assert "project file:" in result.stdout
    assert str(fixtures_dir / "valid.toml") in result.stdout
    assert "test@example.com" not in result.stdout


def test_show_resolved_defaults_marked_default(fixtures_dir: Path) -> None:
    # partial.toml only sets entities.PAN.enabled -- threshold/strategy
    # (and the whole maskflow/exclusions sections) fall back to defaults.
    result = runner.invoke(
        app, ["config", "show", "--resolved", "--config", str(fixtures_dir / "partial.toml")]
    )
    assert result.exit_code == 0
    line = next(
        line for line in result.stdout.splitlines() if line.startswith("entities.PAN.threshold")
    )
    assert "null" in line
    assert "(default)" in line
