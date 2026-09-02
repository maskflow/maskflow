"""Session-scoped masking: unlike mask()/mask_with_policy() (call-scoped --
counters and value->token identity both reset every call), a Session keeps
that identity stable for as long as the session is open. That matters for a
multi-turn agent: two independent mask() calls can each hand out "<PHONE_1>"
for two *different* phone numbers, and anything that correlates tokens
across calls (the LLM itself, or downstream code) then sees the same token
mean two different things. A Session fixes that by holding its
counters/value->token cache/reserved-token set for its whole lifetime
instead of starting fresh per call.

Not thread-safe: see docs/agent-sessions.md. AsyncSession wraps Session via
asyncio.to_thread -- non-invasive (no core changes), but the same
not-shared-across-concurrent-callers caveat applies to it too.
"""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from typing import Any

from maskflow_core import (
    Mapping,
    MappingEntry,
    PIIType,
    Span,
    Strategy,
    detect,
    detect_patterns_only,
    unmask,
)
from maskflow_core.config import CompiledConfig, RootConfig, compile_config
from maskflow_core.detection import DEFAULT_MIN_CONFIDENCE
from maskflow_core.masking import surrogate_substitute
from maskflow_core.strategies import apply_strategy

from ._config import get_ambient_config

# Same collision rule masking.py's mask() applies: input text that already
# contains a placeholder-lookalike substring (e.g. someone's prompt literally
# contains "<EMAIL_1>") must never collide with a token this module assigns.
_RESERVED_TOKEN_RE = re.compile(r"<[A-Z_]+_\d+(?:_[0-9a-f]+)?>")

_DEFAULT_MAX_DEPTH = 32
_DEFAULT_MAX_ITEMS = 10_000

# Bumped only on a breaking change to snapshot()'s dict shape. restore()
# rejects an unknown version rather than silently mis-parsing a payload
# written by a newer maskflow-sdk.
_SNAPSHOT_VERSION = 1


class SessionClosedError(RuntimeError):
    """Raised by any Session/AsyncSession call made after close() (explicit
    or TTL expiry) -- the mapping has been purged, so silently no-op'ing or
    re-opening would either restore nothing (confusing) or start a session
    the caller didn't ask for."""


def _unique_token(candidate: str, reserved: set[str]) -> str:
    token = candidate
    while token in reserved:
        token = f"{candidate[:-1]}_{secrets.token_hex(2)}>"
    return token


def _unique_digits(original_digits: str, reserved: set[str]) -> str:
    """A random same-length digit string, never equal to `original_digits`,
    not colliding with `reserved`, and not starting with a spurious leading
    zero that would make int() silently drop a digit on the way back."""
    alphabet = "0123456789"
    first_alphabet = "123456789" if len(original_digits) > 1 else alphabet
    for _ in range(20):
        candidate = secrets.choice(first_alphabet) + "".join(
            secrets.choice(alphabet) for _ in range(len(original_digits) - 1)
        )
        if candidate != original_digits and candidate not in reserved:
            return candidate
    raise RuntimeError("mask_json: could not generate a unique numeric surrogate")


class Session:
    """Value->placeholder identity stable for the whole session. Use as a
    context manager (`with maskflow.session() as s: ...`) or call close()
    explicitly; either purges the mapping. `ttl_seconds` (default 3600,
    `None` to disable) is enforced lazily -- checked on each call, same
    pattern as maskflow_core.InMemoryMappingStore."""

    def __init__(
        self,
        *,
        ttl_seconds: float | None = 3600,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        config: RootConfig | None = None,
        patterns_only: bool = False,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._min_confidence = min_confidence
        # patterns_only=True skips the NER pass entirely (detect_patterns_only
        # instead of detect) -- no spaCy load, no per-document parse. Trades
        # bare-name / address coverage for a large latency/throughput win, the
        # same tradeoff maskflow_core.logging_filter already makes. Used by
        # maskflow-gateway's MASKFLOW_GATEWAY_NER=0 mode.
        self._patterns_only = patterns_only
        self._expires_at = None if ttl_seconds is None else time.monotonic() + ttl_seconds
        self._closed = False
        self._mapping = Mapping()
        self._counters: dict[PIIType, int] = {}
        self._value_tokens: dict[tuple[PIIType, str], str] = {}
        # Separate from _value_tokens: a numeric leaf's surrogate is a bare
        # digit string, never a "<TYPE_n>" token, so the two caches must not
        # share a key space -- otherwise a value seen first as a string leaf
        # (cached as "<PHONE_1>") could be looked up again from the numeric
        # path and fed into int(), which would raise.
        self._numeric_tokens: dict[tuple[PIIType, str], str] = {}
        # REDACT/MASK/HASH substitutes -- deterministic (or constant) per
        # value, so caching here is a recomputation avoidance, not a
        # correctness requirement (mirrors mask_with_policy()'s
        # substitute_cache).
        self._policy_substitute_cache: dict[tuple[PIIType, Strategy, str], str] = {}
        self._reserved: set[str] = set()
        # Compiled once at construction, not per .mask() call -- a session
        # is long-lived, and re-registering custom patterns/recompiling
        # regex on every call would be wasteful. config=None uses whatever
        # the process-level ambient .maskflowrc cache resolves to.
        self._compiled: CompiledConfig = compile_config(
            config if config is not None else get_ambient_config().config
        )

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._closed = True
        self._mapping = Mapping()
        self._counters.clear()
        self._value_tokens.clear()
        self._numeric_tokens.clear()
        self._policy_substitute_cache.clear()
        self._reserved.clear()

    def _check_open(self) -> None:
        if self._closed:
            raise SessionClosedError("Session is closed; its mapping has been purged.")
        if self._expires_at is not None and time.monotonic() >= self._expires_at:
            self.close()
            raise SessionClosedError(
                f"Session expired after ttl_seconds={self._ttl_seconds}; its mapping has "
                "been purged."
            )

    def _detect(self, text: str, threshold: float) -> list[Span]:
        """Route to the NER-inclusive detect() or the pattern-only pass,
        per the session's `patterns_only` flag. Config-derived kwargs apply
        either way; detect_patterns_only() just doesn't take the two
        exclusion kwargs (see maskflow_core.detection), so they're dropped
        in that branch -- exclusions are rare and NER-off is a deliberate
        coverage/speed tradeoff already."""
        kwargs = self._compiled.detect_kwargs()
        if self._patterns_only:
            return detect_patterns_only(
                text,
                min_confidence=threshold,
                per_entity_threshold=kwargs["per_entity_threshold"],
                disabled_types=kwargs["disabled_types"],
                extra_patterns=kwargs["extra_patterns"],
            )
        return detect(text, min_confidence=threshold, **kwargs)

    def _substitute_for(self, entity_type: PIIType, value: str) -> str:
        """Session-scoped token for (entity_type, value): the same pair
        always returns the same token, and a new pair mints the next
        counter -- this is the identity guarantee the whole module exists
        for."""
        cache_key = (entity_type, value)
        token = self._value_tokens.get(cache_key)
        if token is not None:
            return token
        self._counters[entity_type] = self._counters.get(entity_type, 0) + 1
        candidate = f"<{entity_type.value}_{self._counters[entity_type]}>"
        token = _unique_token(candidate, self._reserved)
        self._reserved.add(token)
        self._value_tokens[cache_key] = token
        self._mapping[token] = MappingEntry(
            token=token,
            entity_type=entity_type,
            strategy=Strategy.REPLACE,
            reversible=True,
            original=value,
        )
        return token

    def _surrogate_for(self, span: Span) -> str:
        """Session-scoped SURROGATE identity, mirroring _substitute_for()'s
        REPLACE identity: the same (entity_type, value) pair always
        returns the same surrogate for the life of the session. Sharing
        _value_tokens' key space with REPLACE is safe -- self._compiled's
        strategy-per-entity-type is fixed for the session's whole
        lifetime, so a given entity_type only ever routes through one
        strategy branch, never both."""
        cache_key = (span.entity_type, span.text)
        token = self._value_tokens.get(cache_key)
        if token is not None:
            return token
        self._counters[span.entity_type] = self._counters.get(span.entity_type, 0) + 1
        fallback_candidate = f"<{span.entity_type.value}_{self._counters[span.entity_type]}>"
        substitute = surrogate_substitute(span, self._reserved, fallback_candidate)
        self._reserved.add(substitute)
        self._value_tokens[cache_key] = substitute
        self._mapping[substitute] = MappingEntry(
            token=substitute,
            entity_type=span.entity_type,
            strategy=Strategy.SURROGATE,
            reversible=True,
            original=span.text,
        )
        return substitute

    def _policy_substitute_for(self, span: Span, strategy: Strategy) -> str:
        """REDACT/MASK/HASH: not addressable in masked_text (may repeat
        across distinct originals by design), recorded in self._mapping
        under a distinct audit_token for audit purposes only -- mirrors
        mask_with_policy()'s non-REPLACE/SURROGATE branch, sharing the
        same per-entity-type counter REPLACE/SURROGATE already use."""
        cache_key = (span.entity_type, strategy, span.text)
        substitute = self._policy_substitute_cache.get(cache_key)
        if substitute is not None:
            return substitute
        self._counters[span.entity_type] = self._counters.get(span.entity_type, 0) + 1
        audit_token = f"<{span.entity_type.value}_{self._counters[span.entity_type]}>"
        substitute = apply_strategy(
            span, strategy, self._compiled.policy.mask_config, self._compiled.policy.hash_config
        )
        self._policy_substitute_cache[cache_key] = substitute
        self._mapping[audit_token] = MappingEntry(
            token=audit_token,
            entity_type=span.entity_type,
            strategy=strategy,
            reversible=False,
            original=span.text,
        )
        return substitute

    def _substitute_for_span(self, span: Span) -> str:
        strategy = self._compiled.policy.strategy_for(span.entity_type)
        if strategy is Strategy.REPLACE:
            return self._substitute_for(span.entity_type, span.text)
        if strategy is Strategy.SURROGATE:
            return self._surrogate_for(span)
        return self._policy_substitute_for(span, strategy)

    def mask(self, text: str, *, min_confidence: float | None = None) -> str:
        self._check_open()
        threshold = self._min_confidence if min_confidence is None else min_confidence
        self._reserved.update(_RESERVED_TOKEN_RE.findall(text))

        spans = self._detect(text, threshold)
        pieces: list[str] = []
        cursor = 0
        for span in spans:  # detect() returns non-overlapping spans sorted by start
            substitute = self._substitute_for_span(span)
            pieces.append(text[cursor : span.start])
            pieces.append(substitute)
            cursor = span.end
        pieces.append(text[cursor:])
        return "".join(pieces)

    def _mask_numeric_leaf(self, value: int, threshold: float) -> int:
        # Threshold/disabled/custom/exclusions apply here same as string
        # leaves -- but the numeric-surrogate scheme itself is used
        # regardless of the entity's configured strategy: swapping a JSON
        # int leaf for a string would break mask_json()'s documented
        # "leaf's JSON type never changes" invariant. Deliberate scope
        # boundary, not an oversight.
        sign = "-" if value < 0 else ""
        digits = str(abs(value))
        spans = self._detect(digits, threshold)
        if len(spans) != 1 or spans[0].start != 0 or spans[0].end != len(digits):
            return value  # no single span covers the whole number -- leave it alone

        span = spans[0]
        cache_key = (span.entity_type, digits)
        cached = self._numeric_tokens.get(cache_key)
        if cached is not None:
            return int(sign + cached)

        surrogate_digits = _unique_digits(digits, self._reserved)
        self._reserved.add(surrogate_digits)
        self._numeric_tokens[cache_key] = surrogate_digits
        self._mapping[surrogate_digits] = MappingEntry(
            token=surrogate_digits,
            entity_type=span.entity_type,
            strategy=Strategy.SURROGATE,
            reversible=True,
            original=digits,
        )
        return int(sign + surrogate_digits)

    def mask_json(
        self,
        value: Any,
        *,
        min_confidence: float | None = None,
        max_depth: int = _DEFAULT_MAX_DEPTH,
        max_items: int = _DEFAULT_MAX_ITEMS,
    ) -> Any:
        """Walk a JSON-shaped structure (dict/list/tuple/str/int/float/bool/
        None), masking string leaves and full-value numeric leaves. Dict
        keys are never touched. A numeric leaf that is PII is replaced with
        a same-digit-count int, never a string -- the leaf's JSON type never
        changes. `max_depth`/`max_items` bound recursion and total work
        against adversarial input; both raise ValueError when exceeded."""
        self._check_open()
        threshold = self._min_confidence if min_confidence is None else min_confidence
        items_visited = 0

        def walk(node: Any, depth: int) -> Any:
            nonlocal items_visited
            if depth > max_depth:
                raise ValueError(f"mask_json: exceeded max_depth={max_depth}")
            items_visited += 1
            if items_visited > max_items:
                raise ValueError(f"mask_json: exceeded max_items={max_items}")

            if isinstance(node, dict):
                return {key: walk(child, depth + 1) for key, child in node.items()}
            if isinstance(node, list):
                return [walk(child, depth + 1) for child in node]
            if isinstance(node, tuple):
                return tuple(walk(child, depth + 1) for child in node)
            if isinstance(node, str):
                return self.mask(node, min_confidence=threshold)
            if isinstance(node, bool) or node is None:
                return node  # bool checked before int: bool is an int subclass
            if isinstance(node, int):
                return self._mask_numeric_leaf(node, threshold)
            return node  # float and any other leaf type: passthrough (see module docstring)

        return walk(value, 0)

    def unmask(self, text: str) -> str:
        self._check_open()
        return unmask(text, self._mapping)

    @property
    def mapping(self) -> Mapping:
        """The session's current token -> MappingEntry map. Read it to build
        an incremental unmasker for a streamed response, or to inspect what
        has been detected so far. Mutating it directly is unsupported --
        go through mask()/mask_json(). Holds raw PII; never log it."""
        self._check_open()
        return self._mapping

    def snapshot(self) -> bytes:
        """Serialize this session's full masking state to a UTF-8 JSON blob:
        the token<->original mapping plus every identity cache (counters,
        value->token, numeric surrogates, policy substitutes, reserved
        tokens). Enough for restore() to continue minting tokens exactly
        where this session left off.

        The blob contains raw PII (that's what a Mapping is) -- it is never
        logged or printed by this method, and a caller persisting it is
        choosing to persist plaintext. maskflow-gateway encrypts it
        (AES-GCM) before it touches Redis. Not stable across a
        `_SNAPSHOT_VERSION` bump; restore() rejects a version it doesn't
        know.
        """
        self._check_open()
        payload = {
            "v": _SNAPSHOT_VERSION,
            "patterns_only": self._patterns_only,
            "mapping": self._mapping.to_json(),
            "counters": {t.value: n for t, n in self._counters.items()},
            "value_tokens": [
                [t.value, value, token] for (t, value), token in self._value_tokens.items()
            ],
            "numeric_tokens": [
                [t.value, value, token] for (t, value), token in self._numeric_tokens.items()
            ],
            "policy_substitute_cache": [
                [t.value, strategy.value, value, sub]
                for (t, strategy, value), sub in self._policy_substitute_cache.items()
            ],
            "reserved": sorted(self._reserved),
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def restore(self, blob: bytes) -> None:
        """Repopulate this session from a snapshot() blob, replacing any
        state it currently holds. The session must be open, and should have
        been constructed with the same `config=` the snapshot was taken
        under -- restore() does not carry the compiled config (regex
        objects don't serialize), it carries the *results* of masking so
        far. TTL is whatever this session was opened with, not the
        original's."""
        self._check_open()
        data = json.loads(blob.decode("utf-8"))
        version = data.get("v")
        if version != _SNAPSHOT_VERSION:
            raise ValueError(
                f"Unsupported session snapshot version {version!r} "
                f"(this maskflow-sdk writes/reads v{_SNAPSHOT_VERSION})."
            )
        self._patterns_only = bool(data["patterns_only"])
        self._mapping = Mapping.from_json(data["mapping"])
        self._counters = {PIIType.register(t): n for t, n in data["counters"].items()}
        self._value_tokens = {
            (PIIType.register(t), value): token for t, value, token in data["value_tokens"]
        }
        self._numeric_tokens = {
            (PIIType.register(t), value): token for t, value, token in data["numeric_tokens"]
        }
        self._policy_substitute_cache = {
            (PIIType.register(t), Strategy(strategy), value): sub
            for t, strategy, value, sub in data["policy_substitute_cache"]
        }
        self._reserved = set(data["reserved"])


class AsyncSession:
    """Non-invasive async wrapper: each call runs the underlying (sync)
    Session method via asyncio.to_thread, so it never blocks the event loop.
    Sequential `await`s on one AsyncSession are safe; asyncio.gather()-ing
    multiple calls on the *same* instance is not -- see docs/agent-sessions.md."""

    def __init__(
        self,
        *,
        ttl_seconds: float | None = 3600,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        config: RootConfig | None = None,
        patterns_only: bool = False,
    ) -> None:
        self._session = Session(
            ttl_seconds=ttl_seconds,
            min_confidence=min_confidence,
            config=config,
            patterns_only=patterns_only,
        )

    async def __aenter__(self) -> AsyncSession:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        await asyncio.to_thread(self._session.close)

    async def mask(self, text: str, *, min_confidence: float | None = None) -> str:
        return await asyncio.to_thread(self._session.mask, text, min_confidence=min_confidence)

    async def mask_json(
        self,
        value: Any,
        *,
        min_confidence: float | None = None,
        max_depth: int = _DEFAULT_MAX_DEPTH,
        max_items: int = _DEFAULT_MAX_ITEMS,
    ) -> Any:
        return await asyncio.to_thread(
            self._session.mask_json,
            value,
            min_confidence=min_confidence,
            max_depth=max_depth,
            max_items=max_items,
        )

    async def unmask(self, text: str) -> str:
        return await asyncio.to_thread(self._session.unmask, text)

    async def snapshot(self) -> bytes:
        return await asyncio.to_thread(self._session.snapshot)

    async def restore(self, blob: bytes) -> None:
        await asyncio.to_thread(self._session.restore, blob)


def session(
    *,
    ttl_seconds: float | None = 3600,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    config: RootConfig | None = None,
    patterns_only: bool = False,
) -> Session:
    """Open a session-scoped masking context: value->placeholder identity is
    stable for as long as it's open (or until ttl_seconds elapses). Use as a
    context manager so the mapping is purged on exit:

        with maskflow.session() as s:
            prompt = s.mask(user_input)
            args = s.mask_json(tool_args)
            reply = s.unmask(response)

    `config=None` (the default) uses the ambient .maskflowrc config
    discovered from the filesystem, compiled once when the session opens.
    Passing `config=` explicitly bypasses discovery entirely -- see
    `maskflow.mask()`'s docstring for what a resolved config can change.
    """
    return Session(
        ttl_seconds=ttl_seconds,
        min_confidence=min_confidence,
        config=config,
        patterns_only=patterns_only,
    )


def async_session(
    *,
    ttl_seconds: float | None = 3600,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    config: RootConfig | None = None,
    patterns_only: bool = False,
) -> AsyncSession:
    """Async counterpart to session() -- see AsyncSession."""
    return AsyncSession(
        ttl_seconds=ttl_seconds,
        min_confidence=min_confidence,
        config=config,
        patterns_only=patterns_only,
    )
