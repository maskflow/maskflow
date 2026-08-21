"""Pydantic schema for .maskflowrc. Every model uses extra="forbid" so an
unknown key is a hard validation error (see errors.py for the
did-you-mean-annotated report) rather than a silently-ignored typo -- see
CLAUDE.md: "a typo'd entity silently disabling detection is a security
bug."

Reuses maskflow_core.strategies.Strategy directly rather than duplicating
it -- an invalid strategy name gets pydantic's own enum error for free.
"""

from __future__ import annotations

from typing import Annotated

from maskflow_core.strategies import Strategy
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .redos import check_pattern_safety_with_probe

# Same shape PIIType.register() requires (entities.py): UPPER_SNAKE,
# starting with a letter so it's also a valid Python identifier.
EntityName = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]*$")]


class MaskflowSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packs: list[str] = Field(default_factory=list)
    default_strategy: Strategy = Strategy.REPLACE


class EntityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    # None means "inherit the global default" -- distinct from "explicitly
    # set to the same value as the default". Merge happens on raw dicts
    # before this model is ever built (see merge.py), so this distinction
    # survives layering.
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    strategy: Strategy | None = None


class CustomEntityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str
    score: float = Field(ge=0.0, le=1.0)
    context: list[str] = Field(default_factory=list)

    @field_validator("pattern")
    @classmethod
    def _pattern_is_safe(cls, value: str) -> str:
        check_pattern_safety_with_probe(value)
        return value


class ExclusionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)

    @field_validator("patterns")
    @classmethod
    def _patterns_are_safe(cls, value: list[str]) -> list[str]:
        for pattern in value:
            check_pattern_safety_with_probe(pattern)
        return value


class RootConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maskflow: MaskflowSection = Field(default_factory=MaskflowSection)
    entities: dict[EntityName, EntityConfig] = Field(default_factory=dict)
    custom: dict[EntityName, CustomEntityConfig] = Field(default_factory=dict)
    exclusions: ExclusionsConfig = Field(default_factory=ExclusionsConfig)
