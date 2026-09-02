"""Incremental unmask for a streamed response.

The upstream model streams the masked text back in arbitrary chunks, and a
placeholder like ``<PERSON_NAME_1>`` can be split across two (or ten) of
them -- or across two SSE frames, with JSON/protocol punctuation in
between. We cannot forward a partial placeholder to the client (it would
render as literal ``<PERSON_NA`` followed later by the real name), and we
will not buffer the whole response (that defeats streaming).

``StreamingUnmasker`` keeps a small rolling buffer and a character trie of
the session's active placeholders. On each ``feed()`` it emits the longest
prefix of everything seen so far that is *certain* -- either a completed
placeholder (replaced with its original) or a character that provably
cannot begin any placeholder -- and retains only the trailing bytes that
could still grow into a placeholder. ``flush()`` at end-of-stream releases
whatever is left verbatim.

Correctness contract (verified by the fuzz suite): for any chunking of a
masked text ``T``, ``"".join(feed(chunk) for chunk in chunks) + flush()``
equals ``maskflow_core.unmask(T, mapping)``.

This relies on three properties the mask side guarantees:

1. Placeholder grammar ``<[A-Z_]+_\\d+(_[0-9a-f]+)?>`` -- pure ASCII, and
   ``>`` occurs only as the final character.
2. No placeholder is a prefix of another (every one ends in ``>``, which
   appears nowhere else) -- so the longest match at a position is *the*
   match and a completed placeholder can never be extended by more input.
3. No placeholder occurs as a substring of any original value -- the mask
   side reserves every placeholder-lookalike found anywhere in the input,
   so a substituted original never needs re-scanning.

Property 3 is *checked* at construction. If it does not hold (not expected
for gateway-minted mappings), the unmasker falls back to buffering the
whole response and running ``maskflow_core.unmask`` once at ``flush()`` --
correctness over streaming.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC

from maskflow_core import Mapping, MappingEntry, unmask


def _reversible_pairs(mapping: MappingABC[str, object] | Mapping) -> dict[str, str]:
    """token -> original, for the entries unmask() would actually restore."""
    pairs: dict[str, str] = {}
    for token, value in mapping.items():
        if isinstance(value, MappingEntry):
            if value.reversible:
                pairs[token] = value.original
        else:
            pairs[token] = str(value)
    return pairs


class _TrieNode:
    __slots__ = ("children", "token")

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        # Set to the full token string iff a token ends exactly at this node.
        self.token: str | None = None


# classify() outcomes
_MATCH = "match"  # a complete token starts at the position
_PREFIX = "prefix"  # ran out of buffer still on a live path -- wait for more
_NONE = "none"  # dead end -- this character cannot begin any token


class StreamingUnmasker:
    """Feed streamed masked text in, get safely-unmasked text out.

    One instance per streamed response. Not thread-safe (mutates
    ``self._buffer``); a single response is consumed by a single task.
    """

    def __init__(self, mapping: MappingABC[str, object] | Mapping) -> None:
        self._pairs = _reversible_pairs(mapping)
        self._root = _TrieNode()
        self._max_token_len = 0
        for token in self._pairs:
            self._insert(token)
            self._max_token_len = max(self._max_token_len, len(token))

        # Property 3: no token may be an infix of any original, or a
        # left-to-right streaming pass would diverge from unmask()'s
        # repeated global replace.
        self._safe_incremental = not any(
            tok in original for original in self._pairs.values() for tok in self._pairs
        )
        self._buffer = ""
        # Only used on the (unexpected) non-incremental fallback path.
        self._fallback_mapping = mapping

    def _insert(self, token: str) -> None:
        node = self._root
        for ch in token:
            node = node.children.setdefault(ch, _TrieNode())
        node.token = token

    def _classify(self, s: str, i: int) -> tuple[str, str | None]:
        node = self._root
        j = i
        n = len(s)
        while j < n:
            nxt = node.children.get(s[j])
            if nxt is None:
                return (_NONE, None)
            node = nxt
            j += 1
            if node.token is not None:
                # Property 2: nothing extends a completed token, so this is
                # unambiguously the match.
                return (_MATCH, node.token)
            if j - i > self._max_token_len:
                # Defensive: a live path longer than any real token cannot
                # complete into one.
                return (_NONE, None)
        return (_PREFIX, None)

    def feed(self, chunk: str) -> str:
        if not self._safe_incremental:
            self._buffer += chunk
            return ""
        if not chunk:
            return ""
        self._buffer += chunk
        out: list[str] = []
        i = 0
        n = len(self._buffer)
        while i < n:
            kind, token = self._classify(self._buffer, i)
            if kind == _MATCH:
                assert token is not None
                out.append(self._pairs[token])  # committed -- never re-scanned
                i += len(token)
            elif kind == _PREFIX:
                break  # retain self._buffer[i:] -- it might still become a token
            else:  # _NONE
                out.append(self._buffer[i])
                i += 1
        self._buffer = self._buffer[i:]
        return "".join(out)

    def flush(self) -> str:
        """End of stream: nothing more can arrive, so a retained prefix can
        never complete -- release the buffer, resolving any complete token
        still in it (there should be none) and emitting the rest verbatim.
        """
        if not self._safe_incremental:
            done = unmask(self._buffer, self._fallback_mapping)
            self._buffer = ""
            return done

        out: list[str] = []
        i = 0
        buf = self._buffer
        n = len(buf)
        while i < n:
            kind, token = self._classify(buf, i)
            if kind == _MATCH:
                assert token is not None
                out.append(self._pairs[token])
                i += len(token)
            else:  # _PREFIX or _NONE -- no more input, so emit literally
                out.append(buf[i])
                i += 1
        self._buffer = ""
        return "".join(out)

    @property
    def pending(self) -> str:
        """The currently-retained buffer -- diagnostic only."""
        return self._buffer


def unmask_whole(text: str, mapping: MappingABC[str, object] | Mapping) -> str:
    """The non-streaming reference: feed ``text`` as one chunk, then flush.
    Equal to ``maskflow_core.unmask(text, mapping)`` under the properties
    above; used as the fuzz oracle and for the non-streaming routes."""
    u = StreamingUnmasker(mapping)
    return u.feed(text) + u.flush()
