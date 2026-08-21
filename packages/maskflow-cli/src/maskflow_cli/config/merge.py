"""Layered merge of raw (pre-validation) config dicts, with per-leaf
provenance tracking. Each layer only contains the keys its source actually
set -- no pydantic defaults are injected until after merging, which is what
lets a higher-precedence layer override a single field (e.g.
entities.AADHAAR.threshold) without erasing sibling fields a lower layer
set (e.g. entities.AADHAAR.strategy).

Dict-valued keys merge recursively, at any nesting depth (this also covers
the two dynamic dict levels, entities.<NAME> and custom.<NAME>, with no
special-casing needed). Non-dict values -- including every list field
(packs, exclusions.values, exclusions.patterns, context) -- are whole-value
replace: a higher layer that sets a list overwrites the lower layer's list
entirely, it never appends.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

Source = Literal["default", "user_file", "project_file", "env", "cli"]

SOURCE_LABELS: dict[Source, str] = {
    "default": "default",
    "user_file": "user file",
    "project_file": "project file",
    "env": "env",
    "cli": "flag",
}


@dataclass(frozen=True)
class Provenance:
    source: Source
    location: str | None = None

    def describe(self) -> str:
        label = SOURCE_LABELS[self.source]
        return f"{label}: {self.location}" if self.location else label


@dataclass(frozen=True)
class Layer:
    source: Source
    data: dict[str, Any]
    # Per-leaf-path location (e.g. "./.maskflowrc:8"), falling back to
    # default_location when a specific leaf has no entry (e.g. env vars,
    # where the var name itself -- built in resolve.py -- is more useful
    # than a shared default).
    locations: dict[tuple[str, ...], str] = field(default_factory=dict)
    default_location: str | None = None


def flatten_leaves(
    data: dict[str, Any], prefix: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], Any]]:
    """Every non-dict value in `data`, as (dotted_path_tuple, value)."""
    leaves: list[tuple[tuple[str, ...], Any]] = []
    for key, value in data.items():
        path = prefix + (key,)
        if isinstance(value, dict):
            leaves.extend(flatten_leaves(value, path))
        else:
            leaves.append((path, value))
    return leaves


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_layers(
    layers: Sequence[Layer],
) -> tuple[dict[str, Any], dict[tuple[str, ...], Provenance]]:
    """Merge `layers` lowest-to-highest precedence. Returns the merged raw
    dict (ready for RootConfig.model_validate()) and provenance for every
    leaf any layer actually touched -- leaves neither layer touched (pure
    schema defaults) are the caller's responsibility to fill in as
    Provenance("default") once the model is validated (see resolve.py)."""
    merged: dict[str, Any] = {}
    provenance: dict[tuple[str, ...], Provenance] = {}

    for layer in layers:
        merged = _deep_merge(merged, layer.data)
        for path, _value in flatten_leaves(layer.data):
            location = layer.locations.get(path, layer.default_location)
            provenance[path] = Provenance(source=layer.source, location=location)

    return merged, provenance
