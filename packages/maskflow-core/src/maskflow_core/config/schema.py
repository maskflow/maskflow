"""Schema for .maskflowrc: frozen dataclasses (no pydantic -- see the PR
that introduced this module for why: pydantic+pydantic_core alone is
~8.1MB, over core's <5MB footprint budget) paired with hand-written
validator functions that walk a raw merged dict.

Every validator collects every problem it finds rather than raising on the
first -- a typo'd key silently disabling detection is a security bug (see
CLAUDE.md), so `validate_root_config()` always returns a best-effort
RootConfig *and* the full issue list; callers decide whether a non-empty
issue list is fatal (resolve.py's is).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from ..strategies import Strategy
from .redos import UnsafePatternError, check_pattern_safety_with_probe

# Same shape PIIType.register() requires (entities.py): UPPER_SNAKE,
# starting with a letter.
_ENTITY_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

_TOP_LEVEL_KEYS = {"maskflow", "entities", "custom", "exclusions"}
_MASKFLOW_KEYS = {"packs", "default_strategy"}
_ENTITY_KEYS = {"enabled", "threshold", "strategy"}
_CUSTOM_KEYS = {"pattern", "score", "context"}
_EXCLUSIONS_KEYS = {"values", "patterns"}


@dataclass(frozen=True)
class MaskflowSection:
    packs: list[str] = field(default_factory=list)
    default_strategy: Strategy = Strategy.REPLACE


@dataclass(frozen=True)
class EntityConfig:
    enabled: bool = True
    # None means "inherit the global default" -- distinct from "explicitly
    # set to the same value as the default". Merge happens on raw dicts
    # before this dataclass is ever built (see merge.py), so this
    # distinction survives layering.
    threshold: float | None = None
    strategy: Strategy | None = None


@dataclass(frozen=True)
class CustomEntityConfig:
    pattern: str
    score: float
    context: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExclusionsConfig:
    values: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RootConfig:
    maskflow: MaskflowSection = field(default_factory=MaskflowSection)
    entities: dict[str, EntityConfig] = field(default_factory=dict)
    custom: dict[str, CustomEntityConfig] = field(default_factory=dict)
    exclusions: ExclusionsConfig = field(default_factory=ExclusionsConfig)


@dataclass(frozen=True)
class RawIssue:
    """One validation problem, before provenance (file:line/env-var/flag)
    is attached -- see errors.py's finalize_errors()."""

    path: tuple[str, ...]
    message: str
    suggestion: str | None = None


def _typename(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "table"
    return type(value).__name__


def _closest(word: str, candidates: Any) -> str | None:
    matches = difflib.get_close_matches(word, list(candidates), n=1)
    return matches[0] if matches else None


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _check_unknown_keys(
    data: dict[str, Any], allowed: set[str], path: tuple[str, ...], issues: list[RawIssue]
) -> None:
    for key in data:
        if key not in allowed:
            issues.append(RawIssue(path + (key,), "unknown key", _closest(key, allowed)))


def _parse_strategy(value: Any, path: tuple[str, ...], issues: list[RawIssue]) -> Strategy:
    if not isinstance(value, str):
        issues.append(RawIssue(path, f"must be a string, got {_typename(value)}"))
        return Strategy.REPLACE
    try:
        return Strategy(value)
    except ValueError:
        valid = [s.value for s in Strategy]
        issues.append(
            RawIssue(
                path,
                f"'{value}' is not a valid strategy (expected one of {', '.join(valid)})",
                _closest(value, valid),
            )
        )
        return Strategy.REPLACE


def _parse_unit_float(value: Any, path: tuple[str, ...], issues: list[RawIssue]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        issues.append(
            RawIssue(path, f"must be a number between 0.0 and 1.0, got {_typename(value)}")
        )
        return None
    if not (0.0 <= value <= 1.0):
        issues.append(RawIssue(path, f"must be between 0.0 and 1.0, got {value}"))
        return None
    return float(value)


def _check_pattern(value: str, path: tuple[str, ...], issues: list[RawIssue]) -> bool:
    try:
        check_pattern_safety_with_probe(value)
        return True
    except UnsafePatternError as exc:
        issues.append(RawIssue(path, str(exc)))
        return False


def _validate_maskflow(data: Any, path: tuple[str, ...], issues: list[RawIssue]) -> MaskflowSection:
    if not isinstance(data, dict):
        issues.append(RawIssue(path, f"must be a table, got {_typename(data)}"))
        return MaskflowSection()
    _check_unknown_keys(data, _MASKFLOW_KEYS, path, issues)

    packs: list[str] = []
    if "packs" in data:
        if _is_str_list(data["packs"]):
            packs = list(data["packs"])
        else:
            issues.append(RawIssue(path + ("packs",), "must be a list of strings"))

    default_strategy = Strategy.REPLACE
    if "default_strategy" in data:
        default_strategy = _parse_strategy(
            data["default_strategy"], path + ("default_strategy",), issues
        )

    return MaskflowSection(packs=packs, default_strategy=default_strategy)


def _validate_entities(
    data: Any, path: tuple[str, ...], issues: list[RawIssue]
) -> dict[str, EntityConfig]:
    if not isinstance(data, dict):
        issues.append(RawIssue(path, f"must be a table, got {_typename(data)}"))
        return {}

    result: dict[str, EntityConfig] = {}
    for name, value in data.items():
        entity_path = path + (name,)
        if not _ENTITY_NAME_RE.match(name):
            issues.append(RawIssue(entity_path, "entity name must be UPPER_SNAKE, e.g. AADHAAR"))
            continue
        if not isinstance(value, dict):
            issues.append(RawIssue(entity_path, f"must be a table, got {_typename(value)}"))
            continue
        _check_unknown_keys(value, _ENTITY_KEYS, entity_path, issues)

        enabled = True
        if "enabled" in value:
            if isinstance(value["enabled"], bool):
                enabled = value["enabled"]
            else:
                issues.append(
                    RawIssue(
                        entity_path + ("enabled",),
                        f"must be a boolean, got {_typename(value['enabled'])}",
                    )
                )

        threshold: float | None = None
        if value.get("threshold") is not None:
            threshold = _parse_unit_float(value["threshold"], entity_path + ("threshold",), issues)

        strategy: Strategy | None = None
        if value.get("strategy") is not None:
            strategy = _parse_strategy(value["strategy"], entity_path + ("strategy",), issues)

        result[name] = EntityConfig(enabled=enabled, threshold=threshold, strategy=strategy)

    return result


def _validate_custom(
    data: Any, path: tuple[str, ...], issues: list[RawIssue]
) -> dict[str, CustomEntityConfig]:
    if not isinstance(data, dict):
        issues.append(RawIssue(path, f"must be a table, got {_typename(data)}"))
        return {}

    result: dict[str, CustomEntityConfig] = {}
    for name, value in data.items():
        entity_path = path + (name,)
        if not _ENTITY_NAME_RE.match(name):
            issues.append(
                RawIssue(entity_path, "entity name must be UPPER_SNAKE, e.g. EMPLOYEE_ID")
            )
            continue
        if not isinstance(value, dict):
            issues.append(RawIssue(entity_path, f"must be a table, got {_typename(value)}"))
            continue
        _check_unknown_keys(value, _CUSTOM_KEYS, entity_path, issues)

        pattern: str | None = None
        if "pattern" not in value:
            issues.append(RawIssue(entity_path + ("pattern",), "missing required field 'pattern'"))
        elif not isinstance(value["pattern"], str):
            issues.append(
                RawIssue(
                    entity_path + ("pattern",),
                    f"must be a string, got {_typename(value['pattern'])}",
                )
            )
        elif _check_pattern(value["pattern"], entity_path + ("pattern",), issues):
            pattern = value["pattern"]

        score: float | None = None
        if "score" not in value:
            issues.append(RawIssue(entity_path + ("score",), "missing required field 'score'"))
        else:
            score = _parse_unit_float(value["score"], entity_path + ("score",), issues)

        context: list[str] = []
        if "context" in value:
            if _is_str_list(value["context"]):
                context = list(value["context"])
            else:
                issues.append(RawIssue(entity_path + ("context",), "must be a list of strings"))

        if pattern is not None and score is not None:
            result[name] = CustomEntityConfig(pattern=pattern, score=score, context=context)

    return result


def _validate_exclusions(
    data: Any, path: tuple[str, ...], issues: list[RawIssue]
) -> ExclusionsConfig:
    if not isinstance(data, dict):
        issues.append(RawIssue(path, f"must be a table, got {_typename(data)}"))
        return ExclusionsConfig()
    _check_unknown_keys(data, _EXCLUSIONS_KEYS, path, issues)

    values: list[str] = []
    if "values" in data:
        if _is_str_list(data["values"]):
            values = list(data["values"])
        else:
            issues.append(RawIssue(path + ("values",), "must be a list of strings"))

    patterns: list[str] = []
    if "patterns" in data:
        if _is_str_list(data["patterns"]):
            for index, pattern in enumerate(data["patterns"]):
                if _check_pattern(pattern, path + ("patterns", str(index)), issues):
                    patterns.append(pattern)
        else:
            issues.append(RawIssue(path + ("patterns",), "must be a list of strings"))

    return ExclusionsConfig(values=values, patterns=patterns)


def validate_root_config(merged: dict[str, Any]) -> tuple[RootConfig, list[RawIssue]]:
    """Validate a merged raw config dict, returning a best-effort
    RootConfig (schema defaults fill in for anything invalid/missing) and
    every problem found. An empty issue list means the config is clean."""
    issues: list[RawIssue] = []
    if not isinstance(merged, dict):
        issues.append(RawIssue((), f"config must be a table, got {_typename(merged)}"))
        return RootConfig(), issues

    _check_unknown_keys(merged, _TOP_LEVEL_KEYS, (), issues)

    maskflow = (
        _validate_maskflow(merged["maskflow"], ("maskflow",), issues)
        if "maskflow" in merged
        else MaskflowSection()
    )
    entities = (
        _validate_entities(merged["entities"], ("entities",), issues)
        if "entities" in merged
        else {}
    )
    custom = _validate_custom(merged["custom"], ("custom",), issues) if "custom" in merged else {}
    exclusions = (
        _validate_exclusions(merged["exclusions"], ("exclusions",), issues)
        if "exclusions" in merged
        else ExclusionsConfig()
    )

    root = RootConfig(maskflow=maskflow, entities=entities, custom=custom, exclusions=exclusions)
    return root, issues
