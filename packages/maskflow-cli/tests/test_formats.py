from __future__ import annotations

from pathlib import Path

import pytest
from maskflow_cli.config.formats import format_for_path, load_raw


@pytest.mark.parametrize(
    ("filename", "expected_fmt"),
    [
        ("valid.toml", "toml"),
        ("valid.yaml", "yaml"),
        ("valid.json", "json"),
        (".maskflowrc", "toml"),
    ],
)
def test_format_for_path(filename: str, expected_fmt: str) -> None:
    assert format_for_path(Path(filename)) == expected_fmt


@pytest.mark.parametrize("filename", ["valid.toml", "valid.yaml", "valid.json"])
def test_load_raw_parses_equivalent_data(fixtures_dir: Path, filename: str) -> None:
    data, raw_text, fmt = load_raw(fixtures_dir / filename)
    assert data["maskflow"]["packs"] == ["india"]
    assert data["entities"]["AADHAAR"]["threshold"] == 0.6
    assert data["custom"]["EMPLOYEE_ID"]["score"] == 0.9
    assert data["exclusions"]["values"] == ["test@example.com"]
    assert raw_text
    assert fmt in ("toml", "yaml", "json")


def test_load_raw_bad_toml(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("[maskflow\npacks = [")
    with pytest.raises(ValueError, match="could not parse"):
        load_raw(path)


def test_load_raw_top_level_must_be_table(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[1, 2, 3]")
    with pytest.raises(ValueError, match="table/object"):
        load_raw(path)
