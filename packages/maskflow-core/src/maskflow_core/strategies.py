"""Per-span substitution strategies: what mask_with_policy() puts in place of
a detected Span. REPLACE and SURROGATE substitute a unique per-instance
value the LLM will echo back verbatim, so both are reversible via unmask()
(handled directly in masking.py, which owns the token/collision bookkeeping).
REDACT, MASK, and HASH intentionally collapse different inputs to
similar-shaped (or literally identical) output -- by design, not reversible.
This module implements those three's substitute text; REPLACE/SURROGATE are
resolved by masking.py itself since they need call-scoped state (counters,
the registry of surrogate generators) this module doesn't have.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from enum import Enum

from .entities import Span

_HASH_KEY_ENV = "MASKFLOW_HASH_KEY"


class Strategy(str, Enum):
    REPLACE = "replace"
    REDACT = "redact"
    MASK = "mask"
    HASH = "hash"
    SURROGATE = "surrogate"


# Which strategies substitute a unique-enough value that unmask() can find it
# in masked_text and restore the original. REDACT/MASK/HASH are deliberately
# excluded -- see module docstring.
REVERSIBLE_STRATEGIES = frozenset({Strategy.REPLACE, Strategy.SURROGATE})


@dataclass(frozen=True)
class MaskConfig:
    """Strategy.MASK formatting: reveal the last `reveal_last` alphanumeric
    characters of a span, masking the rest with `mask_char`. Non-alphanumeric
    separators already in the original (dashes, spaces) are preserved, so
    "2345-1234-9012" -> "XXXX-XXXX-9012" rather than a same-length blob with
    the dashes clobbered."""

    reveal_last: int = 4
    mask_char: str = "X"


@dataclass(frozen=True)
class HashConfig:
    """HMAC-SHA256 key for Strategy.HASH. The same original value always
    hashes to the same digest within one key ("stable"); the hash is never
    reversible -- that's what makes it a hash. `key` must be supplied
    explicitly or via MASKFLOW_HASH_KEY (hex-encoded) -- HASH raises a clear
    error otherwise rather than silently hashing with a default/empty key."""

    key: bytes | None = None

    def resolved_key(self) -> bytes:
        if self.key is not None:
            return self.key
        env_value = os.environ.get(_HASH_KEY_ENV)
        if not env_value:
            raise ValueError(
                "Strategy.HASH needs a key: pass HashConfig(key=...) or set "
                f"{_HASH_KEY_ENV} (hex-encoded) in the environment."
            )
        return bytes.fromhex(env_value)


# Alphanumeric, unicode-aware ([^\W_] excludes both non-word chars and "_",
# since \w includes "_" but a masked run of underscores would look like a
# separator rather than a hidden character).
_REVEALABLE_RE = re.compile(r"[^\W_]", re.UNICODE)


def _apply_mask(value: str, config: MaskConfig) -> str:
    positions = [m.start() for m in _REVEALABLE_RE.finditer(value)]
    if config.reveal_last > 0:
        reveal_from = max(0, len(positions) - config.reveal_last)
    else:
        reveal_from = len(positions)
    keep = set(positions[reveal_from:])
    chars = list(value)
    for i in positions:
        if i not in keep:
            chars[i] = config.mask_char
    return "".join(chars)


def _apply_hash(value: str, config: HashConfig) -> str:
    digest = hmac.new(config.resolved_key(), value.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def apply_strategy(
    span: Span,
    strategy: Strategy,
    mask_config: MaskConfig,
    hash_config: HashConfig | None,
) -> str:
    """Compute the substitute text for REDACT/MASK/HASH. REPLACE/SURROGATE
    are never routed here -- masking.py resolves them directly."""
    if strategy is Strategy.REDACT:
        return f"[REDACTED_{span.entity_type.value}]"
    if strategy is Strategy.MASK:
        return _apply_mask(span.text, mask_config)
    if strategy is Strategy.HASH:
        return _apply_hash(span.text, hash_config or HashConfig())
    raise NotImplementedError(
        f"apply_strategy() does not handle {strategy!r} -- REPLACE/SURROGATE "
        "are resolved by masking.py, not here."
    )
