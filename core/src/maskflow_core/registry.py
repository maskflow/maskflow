"""Extension point for packs to add PII types without editing maskflow-core.

A future pack (e.g. maskflow-pack-india) calls register_pattern() to add a new
PIIType plus its regex/validator rule; detect()/mask()/unmask() pick it up
automatically since they all read from the same PATTERNS table this appends to.

This is a manual registration function, not the entry-point-based plugin
auto-discovery ("maskflow.recognizers") described for the target architecture
-- that needs real installable pack packages to build and test against and is
separate follow-up work. This gives packs something to call today.
"""
import re
from typing import Callable

from .entities import PIIType
from .patterns import PATTERNS

Validator = Callable[[str], "float | None"]


def register_pattern(
    pii_type: str,
    regex: re.Pattern,
    base_confidence: float,
    validator: Validator | None = None,
) -> PIIType:
    """Register a new (regex, base_confidence, validator) rule for `pii_type`,
    registering the PIIType itself first if it isn't already known."""
    registered_type = PIIType.register(pii_type)
    PATTERNS.setdefault(registered_type, []).append((regex, base_confidence, validator))
    return registered_type
