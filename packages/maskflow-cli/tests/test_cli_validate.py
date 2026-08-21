from __future__ import annotations

from pathlib import Path

from maskflow_cli.app import app
from typer.testing import CliRunner

runner = CliRunner()


def test_validate_no_config_is_valid() -> None:
    result = runner.invoke(app, ["config", "validate"], env={"HOME": "/nonexistent-home"})
    assert result.exit_code == 0
    assert "Config is valid" in result.stdout


def test_validate_valid_fixture(fixtures_dir: Path) -> None:
    result = runner.invoke(
        app, ["config", "validate", "--config", str(fixtures_dir / "valid.toml")]
    )
    assert result.exit_code == 0
    assert "Config is valid" in result.stdout
    # entity-name soft cross-check warning (no pack-india installed).
    assert "WARNING" in result.stderr


def test_validate_typo_exits_nonzero(fixtures_dir: Path) -> None:
    result = runner.invoke(app, ["config", "validate", "--config", str(fixtures_dir / "typo.toml")])
    assert result.exit_code == 1
    assert "did you mean 'threshold'?" in result.stderr


def test_validate_set_override(fixtures_dir: Path) -> None:
    result = runner.invoke(
        app,
        [
            "config",
            "validate",
            "--config",
            str(fixtures_dir / "valid.toml"),
            "--set",
            "entities.AADHAAR.threshold=0.99",
        ],
    )
    assert result.exit_code == 0


def test_validate_set_bad_pattern_rejected(fixtures_dir: Path) -> None:
    result = runner.invoke(
        app,
        [
            "config",
            "validate",
            "--set",
            "custom.BAD.pattern=(a+)+",
            "--set",
            "custom.BAD.score=0.9",
        ],
    )
    assert result.exit_code == 1
    assert "unsafe pattern" in result.stderr
