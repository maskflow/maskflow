"""Format-agnostic loading of a .maskflowrc file. TOML is primary (an
extensionless `.maskflowrc` is always parsed as TOML, and TOML support is
always available -- stdlib `tomllib` on 3.11+, the `tomli` dependency on
the 3.10 floor). `.yaml`/`.yml` and `.json` are accepted by extension;
YAML additionally requires the optional `maskflow-core[yaml]` extra --
pyyaml is never imported unless a YAML file is actually being read, so a
bare install never pays for it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal

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

_YAML_EXTRA_HINT = (
    "reading a YAML .maskflowrc requires the optional 'yaml' extra -- install maskflow-core[yaml]"
)


def format_for_path(path: Path) -> Format:
    return _EXTENSION_FORMATS.get(path.suffix, "toml")


def load_raw(path: Path) -> tuple[dict[str, Any], str, Format]:
    """Read `path` and return (parsed dict, raw text, format). Raises
    ValueError with a clear message on a parse error -- callers should not
    need to know which underlying library raised."""
    fmt = format_for_path(path)
    raw_text = path.read_text(encoding="utf-8")

    if fmt == "yaml":
        try:
            import yaml
        except ImportError as exc:
            raise ValueError(f"{path}: {_YAML_EXTRA_HINT}") from exc
        try:
            data = yaml.safe_load(raw_text) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: could not parse as YAML: {exc}") from exc
    elif fmt == "toml":
        try:
            data = tomllib.loads(raw_text)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"{path}: could not parse as TOML: {exc}") from exc
    else:
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: could not parse as JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"{path}: top-level {fmt.upper()} value must be a table/object, "
            f"got {type(data).__name__}"
        )

    return data, raw_text, fmt
