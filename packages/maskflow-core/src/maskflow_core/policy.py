"""Per-call strategy configuration for mask_with_policy() -- mirrors
spanset.ResolveConfig's default-plus-per-entity-override shape (see
spanset.py's ResolveConfig.threshold_for/policy_for).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .entities import PIIType
from .strategies import HashConfig, MaskConfig, Strategy


@dataclass(frozen=True)
class MaskPolicy:
    default_strategy: Strategy = Strategy.REPLACE
    per_entity_strategy: dict[PIIType, Strategy] = field(default_factory=dict)
    mask_config: MaskConfig = field(default_factory=MaskConfig)
    # None until Strategy.HASH is actually selected for some entity type --
    # HashConfig.resolved_key() is what raises if no key is ever supplied.
    hash_config: HashConfig | None = None

    def strategy_for(self, entity_type: PIIType) -> Strategy:
        return self.per_entity_strategy.get(entity_type, self.default_strategy)
