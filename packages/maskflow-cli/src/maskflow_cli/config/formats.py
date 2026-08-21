"""Format-agnostic loading of a .maskflowrc file. TOML is primary (an
extensionless `.maskflowrc` is always parsed as TOML); `.yaml`/`.yml`/
`.json` are accepted by extension.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

Format = Literal["toml", "yaml", "json"]

_EXTENSION_FORMATS: dict[str, Format] = {
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


def format_for_path(path: Path) -> Format:
    return _EXTENSION_FORMATS.get(path.suffix, "toml")


def load_raw(path: Path) -> tuple[dict[str, Any], str, Format]:
    """Read `path` and return (parsed dict, raw text, format). Raises
    ValueError with a clear message on a parse error -- callers should not
    need to know which underlying library raised."""
    fmt = format_for_path(path)
    raw_text = path.read_text(encoding="utf-8")

    try:
        if fmt == "toml":
            data = tomllib.loads(raw_text)
        elif fmt == "yaml":
            data = yaml.safe_load(raw_text) or {}
        else:
            data = json.loads(raw_text)
    except (tomllib.TOMLDecodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: could not parse as {fmt.upper()}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"{path}: top-level {fmt.upper()} value must be a table/object, "
            f"got {type(data).__name__}"
        )

    return data, raw_text, fmt
