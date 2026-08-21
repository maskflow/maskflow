"""Compiles a validated RootConfig into the primitives detect()/
mask_with_policy() actually take. Lives in core (not a separate package)
since it only touches core-native types -- MaskPolicy, Strategy, PIIType
-- with zero cross-package import friction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TypedDict

from ..entities import PIIType
from ..policy import MaskPolicy
from ..strategies import Strategy
from .schema import RootConfig


class DetectKwargs(TypedDict):
    """The five keyword-only kwargs detect()/mask_with_policy() both
    accept, typed precisely enough that mypy can verify a `**detect_kwargs()`
    call site against their real signatures (a plain dict[str, object]
    can't be checked that way)."""

    per_entity_threshold: dict[PIIType, float]
    disabled_types: frozenset[PIIType]
    extra_patterns: tuple[tuple[PIIType, re.Pattern[str], float], ...]
    exclusion_values: frozenset[str]
    exclusion_patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class CompiledConfig:
    policy: MaskPolicy
    per_entity_threshold: dict[PIIType, float] = field(default_factory=dict)
    disabled_types: frozenset[PIIType] = frozenset()
    extra_patterns: tuple[tuple[PIIType, re.Pattern[str], float], ...] = ()
    exclusion_values: frozenset[str] = frozenset()
    exclusion_patterns: tuple[re.Pattern[str], ...] = ()

    def is_noop(self) -> bool:
        """True when this config would change nothing about detection or
        masking -- the signal maskflow-sdk uses to call the original,
        untouched mask()/mask_with_policy(MaskPolicy()) code path instead
        of the config-aware one."""
        return (
            not self.per_entity_threshold
            and not self.disabled_types
            and not self.extra_patterns
            and not self.exclusion_values
            and not self.exclusion_patterns
            and not self.policy.per_entity_strategy
            and self.policy.default_strategy is Strategy.REPLACE
        )

    def detect_kwargs(self) -> DetectKwargs:
        """Ready to **-splat into detect()/mask_with_policy()."""
        return DetectKwargs(
            per_entity_threshold=self.per_entity_threshold,
            disabled_types=self.disabled_types,
            extra_patterns=self.extra_patterns,
            exclusion_values=self.exclusion_values,
            exclusion_patterns=self.exclusion_patterns,
        )


def compile_config(root: RootConfig) -> CompiledConfig:
    per_entity_threshold: dict[PIIType, float] = {}
    disabled_types: set[PIIType] = set()
    per_entity_strategy: dict[PIIType, Strategy] = {}

    for name, entity in root.entities.items():
        try:
            pii_type = PIIType(name)
        except ValueError:
            # Not currently registered by any installed pack -- the soft
            # WARNING at resolve_config()/validate time already covers
            # this; skip quietly rather than crash mask() over a pack
            # that simply isn't installed yet.
            continue
        if not entity.enabled:
            disabled_types.add(pii_type)
        if entity.threshold is not None:
            per_entity_threshold[pii_type] = entity.threshold
        if entity.strategy is not None:
            per_entity_strategy[pii_type] = entity.strategy

    extra_patterns: list[tuple[PIIType, re.Pattern[str], float]] = []
    for name, custom in root.custom.items():
        # Unlike entities.<NAME> above, custom.<NAME> is the legitimate way
        # to mint a brand-new ad-hoc type -- .register() rather than a
        # lookup-only PIIType(name).
        pii_type = PIIType.register(name)
        extra_patterns.append((pii_type, re.compile(custom.pattern), custom.score))

    policy = MaskPolicy(
        default_strategy=root.maskflow.default_strategy,
        per_entity_strategy=per_entity_strategy,
    )

    return CompiledConfig(
        policy=policy,
        per_entity_threshold=per_entity_threshold,
        disabled_types=frozenset(disabled_types),
        extra_patterns=tuple(extra_patterns),
        exclusion_values=frozenset(root.exclusions.values),
        exclusion_patterns=tuple(re.compile(p) for p in root.exclusions.patterns),
    )
