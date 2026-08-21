from __future__ import annotations

from pathlib import Path

import pytest
from maskflow_core.config.resolve import ConfigResolutionError, resolve_config


def test_typo_entity_field_suggests_correction(fixtures_dir: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(ConfigResolutionError) as excinfo:
        resolve_config(
            cwd=tmp_path, home=home, env={}, config_path_override=fixtures_dir / "typo.toml"
        )
    report = str(excinfo.value)
    assert "entities.PAN.threshod" in report
    assert "did you mean 'threshold'?" in report
    assert str(fixtures_dir / "typo.toml") in report


def test_two_simultaneous_typos_reported_together(fixtures_dir: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(ConfigResolutionError) as excinfo:
        resolve_config(
            cwd=tmp_path,
            home=home,
            env={},
            config_path_override=fixtures_dir / "two_typos.toml",
        )
    errors = excinfo.value.errors
    paths = {e.path for e in errors}
    assert "maskflw" in paths
    assert "entities.PAN.threshod" in paths
    assert len(errors) == 2


def test_top_level_typo_suggests_correction(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config = tmp_path / ".maskflowrc"
    config.write_text("[exclusons]\nvalues = []\n")
    with pytest.raises(ConfigResolutionError) as excinfo:
        resolve_config(cwd=tmp_path, home=home, env={}, config_path_override=config)
    report = str(excinfo.value)
    assert "did you mean 'exclusions'?" in report
