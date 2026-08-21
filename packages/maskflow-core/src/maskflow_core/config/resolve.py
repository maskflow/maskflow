"""Ties file discovery, environment variables, and CLI overrides together
into one resolved, validated RootConfig with full provenance. This is what
`maskflow config validate`/`show` (maskflow-cli) call, and what
maskflow-sdk's ambient config cache calls too; also usable directly by
anything that wants a resolved config without going through either.

Precedence, lowest to highest: schema defaults < user file < project file
(or --config, which takes the project file's slot) < environment < CLI
--set overrides.
"""

from __future__ import annotations

import difflib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..entities import PIIType
from . import discovery
from .errors import ConfigError, finalize_errors, format_error_report
from .formats import load_raw
from .linemap import build_linemap, lookup_line
from .merge import Layer, Provenance, Source, flatten_leaves, merge_layers
from .schema import RootConfig, validate_root_config

ENV_PREFIX = "MASKFLOW_"
# Existing envs owned by maskflow_core (strategies.py / mapping_store.py)
# for unrelated purposes -- never swept into this config layer.
_RESERVED_ENV_NAMES = {"MASKFLOW_HASH_KEY", "MASKFLOW_MAPPING_KEY"}
_TOP_LEVEL_MASKFLOW_FIELDS = {"packs", "default_strategy"}


@dataclass(frozen=True)
class ConfigWarning:
    message: str


@dataclass(frozen=True)
class ResolvedConfig:
    config: RootConfig
    provenance: dict[tuple[str, ...], Provenance]
    project_file: Path | None
    user_file: Path | None
    warnings: list[ConfigWarning] = field(default_factory=list)


class ConfigResolutionError(Exception):
    """Raised with every problem found (file validation errors,
    unrecognized env vars, malformed --set flags) -- never just the
    first."""

    def __init__(self, errors: list[ConfigError]) -> None:
        self.errors = errors
        super().__init__(format_error_report(errors))


def _file_layer(source: Source, path: Path) -> Layer:
    data, raw_text, fmt = load_raw(path)
    linemap = build_linemap(raw_text, fmt)
    locations: dict[tuple[str, ...], str] = {}
    for leaf_path, _value in flatten_leaves(data):
        line = lookup_line(linemap, leaf_path)
        locations[leaf_path] = f"{path}:{line}" if line is not None else str(path)
    return Layer(source=source, data=data, locations=locations, default_location=str(path))


def _set_path(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    node = data
    for part in path[:-1]:
        node = node.setdefault(part, {})
    node[path[-1]] = value


def _parse_scalar(raw: str) -> Any:
    """JSON first (covers numbers/bools/lists/null cleanly), then a bare
    comma-list for convenience (e.g. MASKFLOW_PACKS=india,intl), else the
    raw string as-is."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    if "," in raw:
        return [part.strip() for part in raw.split(",")]
    return raw


def _parse_env_key(key: str) -> tuple[str, ...] | None:
    rest = key[len(ENV_PREFIX) :]
    if not rest:
        return None
    parts = rest.split("__")
    section = parts[0].lower()
    if section in _TOP_LEVEL_MASKFLOW_FIELDS and len(parts) == 1:
        return ("maskflow", section)
    if section in ("entities", "custom") and len(parts) == 3:
        return (section, parts[1], parts[2].lower())
    if section == "exclusions" and len(parts) == 2:
        return ("exclusions", parts[1].lower())
    return None


def _build_env_layer(env: Mapping[str, str]) -> tuple[Layer, list[ConfigError]]:
    data: dict[str, Any] = {}
    locations: dict[tuple[str, ...], str] = {}
    errors: list[ConfigError] = []

    for key, raw_value in env.items():
        if not key.startswith(ENV_PREFIX) or key in _RESERVED_ENV_NAMES:
            continue
        path = _parse_env_key(key)
        if path is None:
            errors.append(
                ConfigError(
                    path=key,
                    message="unrecognized MASKFLOW_* environment variable",
                    prefix="env",
                    suggestion=None,
                )
            )
            continue
        _set_path(data, path, _parse_scalar(raw_value))
        locations[path] = key

    return Layer(source="env", data=data, locations=locations), errors


def _build_cli_layer(cli_sets: list[str]) -> tuple[Layer, list[ConfigError]]:
    data: dict[str, Any] = {}
    locations: dict[tuple[str, ...], str] = {}
    errors: list[ConfigError] = []

    for item in cli_sets:
        if "=" not in item:
            errors.append(
                ConfigError(
                    path=item, message="--set must be KEY=VALUE", prefix="flag", suggestion=None
                )
            )
            continue
        key, _, raw_value = item.partition("=")
        path = tuple(key.strip().split("."))
        if not key.strip() or any(not p for p in path):
            errors.append(
                ConfigError(
                    path=item,
                    message="--set key must be a dotted path, e.g. entities.AADHAAR.threshold",
                    prefix="flag",
                    suggestion=None,
                )
            )
            continue
        _set_path(data, path, _parse_scalar(raw_value))
        locations[path] = f"--set {item}"

    return Layer(source="cli", data=data, locations=locations), errors


def _check_entity_names(config: RootConfig) -> list[ConfigWarning]:
    """Soft, best-effort cross-check against currently-registered PIITypes.
    A miss is a WARNING, never a hard failure -- the pack that would
    register a name (e.g. maskflow-pack-india) may simply not be installed
    yet, which is a legitimate state, not a config bug.

    Deliberately does NOT import any pack itself: maskflow-pack-intl (and
    any other pack) depends on maskflow-core, so core importing a pack
    back would be a circular dependency. This just reads whatever's
    already registered -- callers (maskflow-cli's app.py, maskflow-sdk's
    __init__.py) are responsible for importing their packs first, which
    both already do for their own reasons.
    """
    known = {str(t) for t in PIIType.values()}
    warnings: list[ConfigWarning] = []
    for section, names in (("entities", config.entities), ("custom", config.custom)):
        for name in names:
            if name in known:
                continue
            suggestion = difflib.get_close_matches(name, known, n=1)
            hint = f" (did you mean '{suggestion[0]}'?)" if suggestion else ""
            warnings.append(
                ConfigWarning(
                    f"{section}.{name}: no currently-installed pack registers this "
                    f"entity type{hint} -- if you expect a pack to provide it, make "
                    "sure it's installed."
                )
            )
    return warnings


def resolve_config(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
    config_path_override: Path | None = None,
    cli_sets: list[str] | None = None,
) -> ResolvedConfig:
    env = env if env is not None else os.environ
    cwd = cwd if cwd is not None else Path.cwd()
    home = home if home is not None else Path.home()
    cli_sets = cli_sets or []

    layers: list[Layer] = []

    user_file = discovery.find_user_file(home=home)
    if user_file is not None:
        layers.append(_file_layer("user_file", user_file))

    if config_path_override is not None:
        project_file: Path | None = config_path_override
        layers.append(_file_layer("project_file", config_path_override))
    else:
        project_file = discovery.find_project_file(cwd=cwd, home=home)
        if project_file is not None:
            layers.append(_file_layer("project_file", project_file))

    env_layer, env_errors = _build_env_layer(env)
    if env_layer.data:
        layers.append(env_layer)

    cli_layer, cli_errors = _build_cli_layer(cli_sets)
    if cli_layer.data:
        layers.append(cli_layer)

    pre_errors = env_errors + cli_errors
    if pre_errors:
        raise ConfigResolutionError(pre_errors)

    merged, provenance = merge_layers(layers)

    config, issues = validate_root_config(merged)
    if issues:
        raise ConfigResolutionError(finalize_errors(issues, provenance))

    for leaf_path, _value in flatten_leaves(asdict(config)):
        provenance.setdefault(leaf_path, Provenance(source="default"))

    return ResolvedConfig(
        config=config,
        provenance=provenance,
        project_file=project_file,
        user_file=user_file,
        warnings=_check_entity_names(config),
    )
