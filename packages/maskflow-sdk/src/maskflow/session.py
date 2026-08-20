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
import re
import secrets
import time
from typing import Any

from maskflow_core import Mapping, MappingEntry, PIIType, Strategy, detect, unmask
from maskflow_core.detection import DEFAULT_MIN_CONFIDENCE

# Same collision rule masking.py's mask() applies: input text that already
# contains a placeholder-lookalike substring (e.g. someone's prompt literally
# contains "<EMAIL_1>") must never collide with a token this module assigns.
_RESERVED_TOKEN_RE = re.compile(r"<[A-Z_]+_\d+(?:_[0-9a-f]+)?>")

_DEFAULT_MAX_DEPTH = 32
_DEFAULT_MAX_ITEMS = 10_000


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
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._min_confidence = min_confidence
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
        self._reserved: set[str] = set()

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

    def mask(self, text: str, *, min_confidence: float | None = None) -> str:
        self._check_open()
        threshold = self._min_confidence if min_confidence is None else min_confidence
        self._reserved.update(_RESERVED_TOKEN_RE.findall(text))

        spans = detect(text, min_confidence=threshold)
        pieces: list[str] = []
        cursor = 0
        for span in spans:  # detect() returns non-overlapping spans sorted by start
            token = self._substitute_for(span.entity_type, span.text)
            pieces.append(text[cursor : span.start])
            pieces.append(token)
            cursor = span.end
        pieces.append(text[cursor:])
        return "".join(pieces)

    def _mask_numeric_leaf(self, value: int, threshold: float) -> int:
        sign = "-" if value < 0 else ""
        digits = str(abs(value))
        spans = detect(digits, min_confidence=threshold)
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
    ) -> None:
        self._session = Session(ttl_seconds=ttl_seconds, min_confidence=min_confidence)

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


def session(
    *,
    ttl_seconds: float | None = 3600,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> Session:
    """Open a session-scoped masking context: value->placeholder identity is
    stable for as long as it's open (or until ttl_seconds elapses). Use as a
    context manager so the mapping is purged on exit:

        with maskflow.session() as s:
            prompt = s.mask(user_input)
            args = s.mask_json(tool_args)
            reply = s.unmask(response)
    """
    return Session(ttl_seconds=ttl_seconds, min_confidence=min_confidence)


def async_session(
    *,
    ttl_seconds: float | None = 3600,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> AsyncSession:
    """Async counterpart to session() -- see AsyncSession."""
    return AsyncSession(ttl_seconds=ttl_seconds, min_confidence=min_confidence)
