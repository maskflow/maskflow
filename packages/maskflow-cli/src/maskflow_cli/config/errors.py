"""Turns a pydantic ValidationError over the merged config into a report a
human can act on: every problem at once (pydantic v2 already aggregates
independent field errors in one pass), each annotated with where it came
from (file:line, env var, or CLI flag) and, for an unknown-key error, a
did-you-mean suggestion against the real field names at that nesting level.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError

from .merge import SOURCE_LABELS, Provenance
from .schema import RootConfig


def _unwrap_model(annotation: Any) -> type[BaseModel] | None:
    origin = get_origin(annotation)
    if origin is dict:
        args = get_args(annotation)
        if len(args) == 2 and isinstance(args[1], type) and issubclass(args[1], BaseModel):
            return args[1]
        return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _model_for_loc(loc: tuple[Any, ...]) -> type[BaseModel]:
    """Which model's field names the last element of `loc` should have
    matched against -- walks RootConfig's structure, stepping through
    dynamic dict keys (entity/custom names) without losing the dict's
    value-model type."""
    model: type[BaseModel] = RootConfig
    for part in loc[:-1]:
        fields = model.model_fields
        if part in fields:
            unwrapped = _unwrap_model(fields[part].annotation)
            if unwrapped is not None:
                model = unwrapped
        # else: `part` is a dynamic dict key (e.g. an entity name) --
        # `model` already holds the dict's value-model type from the
        # previous iteration, so there's nothing to update.
    return model


def _error_prefix(prov: Provenance | None) -> str:
    if prov is None:
        return "?"
    if prov.source in ("user_file", "project_file") and prov.location:
        return prov.location
    if prov.location:
        return f"{SOURCE_LABELS[prov.source]} ({prov.location})"
    return SOURCE_LABELS[prov.source]


def _provenance_for(
    loc: tuple[str, ...], provenance: dict[tuple[str, ...], Provenance]
) -> Provenance | None:
    for end in range(len(loc), 0, -1):
        prov = provenance.get(loc[:end])
        if prov is not None:
            return prov
    return None


@dataclass(frozen=True)
class ConfigError:
    path: str
    message: str
    prefix: str
    suggestion: str | None


def build_error_report(
    exc: ValidationError, provenance: dict[tuple[str, ...], Provenance]
) -> list[ConfigError]:
    report: list[ConfigError] = []
    for err in exc.errors():
        loc = tuple(str(p) for p in err["loc"])
        suggestion: str | None = None
        if err["type"] == "extra_forbidden" and loc:
            model = _model_for_loc(err["loc"])
            candidates = list(model.model_fields.keys())
            matches = difflib.get_close_matches(loc[-1], candidates, n=1)
            if matches:
                suggestion = matches[0]

        prov = _provenance_for(loc, provenance)
        report.append(
            ConfigError(
                path=".".join(loc) or "<root>",
                message=err["msg"],
                prefix=_error_prefix(prov),
                suggestion=suggestion,
            )
        )
    return report


def format_error_report(errors: list[ConfigError]) -> str:
    lines = []
    for e in errors:
        line = f"{e.prefix}: {e.path} - {e.message}"
        if e.suggestion:
            line += f" (did you mean '{e.suggestion}'?)"
        lines.append(line)
    return "\n".join(lines)
