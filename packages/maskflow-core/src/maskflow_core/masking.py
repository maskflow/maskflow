"""Pure, stateless mask/unmask. No files, no DB -- the caller owns persistence of
the mapping (see mapping_store.py for an optional, still-caller-invoked, way to
do that persistence).

Offsets throughout this module (and Span.start/end, which they come from) are
Python `str` code-point offsets, not byte offsets -- `text[start:end]` on a
native `str` is code-point-safe, so slicing never splits a multi-byte UTF-8
sequence, a combining mark, or a ZWJ sequence the way a raw byte-offset scheme
could for non-ASCII PII (e.g. a Devanagari name). This is consistent across
detect()/mask()/mask_with_policy() -- there is exactly one offset convention
in this codebase.
"""

import re
import secrets
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence
from typing import NamedTuple

from .detection import DEFAULT_MIN_CONFIDENCE, detect
from .entities import ExplanationStep, PIIType, Span
from .mapping import Mapping, MappingEntry
from .policy import MaskPolicy
from .registry import SURROGATE_GENERATORS
from .strategies import REVERSIBLE_STRATEGIES, Strategy, apply_strategy

# Matches both plain (<EMAIL_1>) and nonce-suffixed (<EMAIL_1_a4f9>) tokens, so
# input text that already contains placeholder-lookalike substrings is detected
# and never collided with.
_RESERVED_TOKEN_RE = re.compile(r"<[A-Z_]+_\d+(?:_[0-9a-f]+)?>")


class MaskResult(NamedTuple):
    masked_text: str
    mapping: dict[str, str]


class PolicyMaskResult(NamedTuple):
    """mask_with_policy()'s return type -- a distinct type from MaskResult
    (rather than a dict[str, str] | Mapping union on the same NamedTuple) so
    `result.mapping` is precisely a Mapping wherever it's used, with no
    isinstance-narrowing needed at every call site."""

    masked_text: str
    mapping: Mapping


def mask(text: str, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> MaskResult:
    """Replace detected PII with `<TYPE_n>` tokens, returning the masked text and a
    {token: original_value} mapping the caller can use to unmask a later response."""
    spans = detect(text, min_confidence=min_confidence)

    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}
    pieces: list[str] = []
    cursor = 0
    # Placeholder-lookalike text already present in the input (e.g. someone's
    # prompt literally contains "<EMAIL_1>") must never collide with a token
    # we assign -- track everything already claimed, real or lookalike.
    reserved: set[str] = set(_RESERVED_TOKEN_RE.findall(text))
    # Same value -> same token within one call, so a repeated PII value reads
    # consistently in the masked output instead of getting a fresh number
    # each time it recurs.
    value_tokens: dict[tuple[str, str], str] = {}

    for span in spans:  # detect() returns non-overlapping spans sorted by start
        entity_type = span.entity_type.value
        cache_key = (entity_type, span.text)
        token = value_tokens.get(cache_key)
        if token is None:
            counters[entity_type] = counters.get(entity_type, 0) + 1
            token = f"<{entity_type}_{counters[entity_type]}>"
            while token in reserved:
                token = f"<{entity_type}_{counters[entity_type]}_{secrets.token_hex(2)}>"
            reserved.add(token)
            value_tokens[cache_key] = token
            mapping[token] = span.text
        pieces.append(text[cursor : span.start])
        pieces.append(token)
        cursor = span.end

    pieces.append(text[cursor:])
    return MaskResult("".join(pieces), mapping)


_DEFAULT_POLICY = MaskPolicy()


def mask_with_policy(
    text: str,
    policy: MaskPolicy = _DEFAULT_POLICY,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    *,
    per_entity_threshold: MappingABC[PIIType, float] | None = None,
    disabled_types: frozenset[PIIType] = frozenset(),
    extra_patterns: Sequence[tuple[PIIType, re.Pattern[str], float]] = (),
    exclusion_values: frozenset[str] = frozenset(),
    exclusion_patterns: Sequence[re.Pattern[str]] = (),
) -> PolicyMaskResult:
    """Like mask(), but each entity type can use any of Strategy.{REPLACE,
    REDACT, MASK, HASH, SURROGATE} per `policy` (see policy.py). Returns a
    Mapping (not a plain dict) recording, per substitution, whether unmask()
    can reverse it -- only REPLACE and SURROGATE can; REDACT/MASK/HASH are
    intentionally lossy (see strategies.py's module docstring).

    The five keyword-only params are forwarded straight to detect() -- see
    its docstring; same "no effect at their defaults" guarantee applies
    here."""
    spans = detect(
        text,
        min_confidence=min_confidence,
        per_entity_threshold=per_entity_threshold,
        disabled_types=disabled_types,
        extra_patterns=extra_patterns,
        exclusion_values=exclusion_values,
        exclusion_patterns=exclusion_patterns,
    )

    entries: dict[str, MappingEntry] = {}
    counters: dict[PIIType, int] = {}
    pieces: list[str] = []
    cursor = 0
    reserved: set[str] = set(_RESERVED_TOKEN_RE.findall(text))
    # Same (entity_type, strategy, original value) -> same substitute text
    # within one call -- for REPLACE/SURROGATE this is what makes repeated
    # values read consistently (and is required for unmask() to work at
    # all); for REDACT/MASK/HASH it's a harmless no-op since those are
    # already deterministic (or constant) per value.
    substitute_cache: dict[tuple[PIIType, Strategy, str], str] = {}

    for span in spans:
        strategy = policy.strategy_for(span.entity_type)
        cache_key = (span.entity_type, strategy, span.text)
        substitute = substitute_cache.get(cache_key)

        if substitute is None:
            counters[span.entity_type] = counters.get(span.entity_type, 0) + 1
            audit_token = f"<{span.entity_type.value}_{counters[span.entity_type]}>"

            if strategy is Strategy.REPLACE:
                substitute = _unique(audit_token, reserved)
                reserved.add(substitute)
            elif strategy is Strategy.SURROGATE:
                substitute = surrogate_substitute(span, reserved, audit_token)
                reserved.add(substitute)
            else:
                substitute = apply_strategy(span, strategy, policy.mask_config, policy.hash_config)
                # Not addressable in masked_text (may repeat across distinct
                # originals by design -- see strategies.py), so it never
                # collides with `reserved`; the *key* used for MappingEntry
                # below still needs to be unique, which audit_token is.

            substitute_cache[cache_key] = substitute
            entry_key = substitute if strategy in REVERSIBLE_STRATEGIES else audit_token
            entries[entry_key] = MappingEntry(
                token=entry_key,
                entity_type=span.entity_type,
                strategy=strategy,
                reversible=strategy in REVERSIBLE_STRATEGIES,
                original=span.text,
            )

        pieces.append(text[cursor : span.start])
        pieces.append(substitute)
        cursor = span.end

    pieces.append(text[cursor:])
    return PolicyMaskResult("".join(pieces), Mapping(entries))


def _unique(candidate: str, reserved: set[str]) -> str:
    """Disambiguate a `<TYPE_n>`-shaped `candidate` against `reserved` with a
    random nonce suffix -- same scheme mask() uses for placeholder-lookalike
    collisions."""
    token = candidate
    while token in reserved:
        token = f"{candidate[:-1]}_{secrets.token_hex(2)}>"
    return token


def surrogate_substitute(span: Span, reserved: set[str], fallback_token: str) -> str:
    """A plausible fake value of the same type as `span`, or a REPLACE-style
    placeholder if no generator is registered for this entity type."""
    generator_entry = SURROGATE_GENERATORS.get(span.entity_type)
    if generator_entry is None:
        span.explanation.append(
            ExplanationStep(
                rule="surrogate", outcome="fallback", detail="no generator registered for this type"
            )
        )
        return _unique(fallback_token, reserved)

    generator, _note = generator_entry
    rng = secrets.SystemRandom()
    for _ in range(20):
        candidate = generator(span.text, rng)
        if candidate not in reserved:
            return candidate
    span.explanation.append(
        ExplanationStep(rule="surrogate", outcome="fallback", detail="generator kept colliding")
    )
    return _unique(fallback_token, reserved)


def unmask(masked_text: str, mapping: dict[str, str] | Mapping) -> str:
    """Restore original values from a mapping produced by `mask()` or
    `mask_with_policy()`. For a Mapping (mask_with_policy()'s return type),
    only entries where `reversible` is true are restored -- REDACT/MASK/HASH
    substitutions are intentionally left as-is (see mask_with_policy())."""
    result = masked_text
    for token, value in mapping.items():
        if isinstance(value, MappingEntry):
            if not value.reversible:
                continue
            original = value.original
        else:
            original = value
        result = result.replace(token, original)
    return result
