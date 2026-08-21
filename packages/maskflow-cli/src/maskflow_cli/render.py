"""Rendering for `maskflow config show`/`show --resolved`. Both redact
exclusions.values in every code path -- those are free-form user text that
could itself be PII-shaped, so the raw literal is never printed (see
CLAUDE.md rule 1: never log/print PII).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import tomli_w
from maskflow_core.config.merge import flatten_leaves
from maskflow_core.config.resolve import ResolvedConfig

_SECTION_ORDER = {"maskflow": 0, "entities": 1, "custom": 2, "exclusions": 3}


def _redact_value(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def _redact_values_list(values: list[str]) -> list[str]:
    return [_redact_value(v) for v in values]


def _sort_key(path: tuple[str, ...]) -> tuple[Any, ...]:
    return (_SECTION_ORDER.get(path[0], 99), *path[1:])


def format_resolved(resolved: ResolvedConfig) -> str:
    """One aligned line per leaf field: `path = value   (origin)`."""
    leaves = flatten_leaves(asdict(resolved.config))
    leaves.sort(key=lambda item: _sort_key(item[0]))

    rows: list[tuple[str, str, str]] = []
    for path, value in leaves:
        if path[0] == "exclusions" and path[-1] == "values":
            value = _redact_values_list(value)
        prov = resolved.provenance.get(path)
        origin = prov.describe() if prov is not None else "default"
        rows.append((".".join(path), json.dumps(value), origin))

    if not rows:
        return ""

    key_width = max(len(key) for key, _, _ in rows)
    value_width = max(len(value) for _, value, _ in rows)
    return "\n".join(
        f"{key.ljust(key_width)} = {value.ljust(value_width)}   ({origin})"
        for key, value, origin in rows
    )


def _strip_none(value: Any) -> Any:
    """TOML has no null type -- drop None-valued keys (e.g. an unset
    EntityConfig.threshold/strategy, meaning "inherit the default") rather
    than fail to serialize them."""
    if isinstance(value, dict):
        return {k: _strip_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_none(v) for v in value]
    return value


def format_show(resolved: ResolvedConfig) -> str:
    """Plain TOML dump of the merged, validated config -- for inspection,
    not guaranteed round-trippable: exclusions.values is redacted, so it
    won't read back as the original values, and unset fields (None) are
    omitted rather than serialized."""
    data = asdict(resolved.config)
    if data.get("exclusions", {}).get("values"):
        data["exclusions"]["values"] = _redact_values_list(data["exclusions"]["values"])
    return tomli_w.dumps(_strip_none(data))
