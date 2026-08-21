from __future__ import annotations

from pathlib import Path

import pytest
from maskflow_cli.config.formats import load_raw
from maskflow_cli.config.linemap import build_linemap, lookup_line


@pytest.mark.parametrize("filename", ["valid.toml", "valid.yaml", "valid.json"])
def test_linemap_resolves_nested_leaf(fixtures_dir: Path, filename: str) -> None:
    _data, raw_text, fmt = load_raw(fixtures_dir / filename)
    linemap = build_linemap(raw_text, fmt)
    line = lookup_line(linemap, ("entities", "AADHAAR", "threshold"))
    assert line is not None
    lines = raw_text.splitlines()
    assert "0.6" in lines[line - 1] or "threshold" in lines[line - 1]


def test_linemap_toml_table_and_key_lines() -> None:
    raw = "[maskflow]\npacks = [\"india\"]\ndefault_strategy = \"replace\"\n"
    linemap = build_linemap(raw, "toml")
    assert linemap[("maskflow",)] == 1
    assert linemap[("maskflow", "packs")] == 2
    assert linemap[("maskflow", "default_strategy")] == 3


def test_lookup_line_falls_back_to_ancestor() -> None:
    linemap: dict[tuple[str, ...], int] = {("entities", "AADHAAR"): 5}
    assert lookup_line(linemap, ("entities", "AADHAAR", "threshold")) == 5


def test_lookup_line_unknown_path_returns_none() -> None:
    assert lookup_line({}, ("nope",)) is None


def test_linemap_json_nested_leaf() -> None:
    raw = '{\n  "entities": {\n    "AADHAAR": {\n      "threshold": 0.6\n    }\n  }\n}\n'
    linemap = build_linemap(raw, "json")
    assert linemap[("entities", "AADHAAR", "threshold")] == 4
