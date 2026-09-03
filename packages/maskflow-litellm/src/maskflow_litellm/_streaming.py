"""Incremental unmask for a streamed LiteLLM response.

``async_post_call_streaming_iterator_hook`` hands us an async iterator of
``ModelResponseStream`` chunks. A placeholder like ``<PERSON_NAME_1>`` can
be split across two ``delta.content`` fragments (or two
``tool_calls[].function.arguments`` fragments), so we cannot just
substring-replace per chunk. ``maskflow.streaming.StreamingUnmasker`` (a
rolling buffer + a trie of the session's active placeholders, fuzz-tested
in maskflow-sdk) emits only what is certain and retains a partial
placeholder until the rest arrives.

One ``StreamingUnmasker`` per stream position:

* ``("content", choice_index)`` for ``delta.content``
* ``("tool_args", choice_index, tool_call_index)`` for a tool call's
  ``arguments`` (placeholders are ASCII with no JSON metacharacters, so the
  same trie logic is correct on a raw argument fragment).

This module has no ``litellm`` import -- it mutates the real upstream chunk
objects in place through duck typing and yields them, delaying each chunk
by one so the last one can carry any ``flush()`` remainder (only non-empty
when the model's output was cut off mid-placeholder, e.g.
``finish_reason="length"``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from maskflow import Session
from maskflow.streaming import StreamingUnmasker
from maskflow_core import Mapping

_MISSING = object()


class _Unmaskers:
    def __init__(self, mapping: Mapping) -> None:
        self._mapping = mapping
        self._by_key: dict[tuple[Any, ...], StreamingUnmasker] = {}

    def get(self, key: tuple[Any, ...]) -> StreamingUnmasker:
        u = self._by_key.get(key)
        if u is None:
            u = self._by_key[key] = StreamingUnmasker(self._mapping)
        return u

    def flush_remainders(self) -> dict[tuple[Any, ...], str]:
        return {key: rem for key, u in self._by_key.items() if (rem := u.flush())}


def _feed_chunk(chunk: Any, unmaskers: _Unmaskers) -> None:
    for choice in getattr(chunk, "choices", None) or []:
        idx = getattr(choice, "index", 0) or 0
        delta = getattr(choice, "delta", None)
        if delta is None:
            continue
        if isinstance(getattr(delta, "content", None), str):
            delta.content = unmaskers.get(("content", idx)).feed(delta.content)
        for call in getattr(delta, "tool_calls", None) or []:
            tc_idx = getattr(call, "index", 0) or 0
            fn = getattr(call, "function", None)
            if fn is not None and isinstance(getattr(fn, "arguments", None), str):
                fn.arguments = unmaskers.get(("tool_args", idx, tc_idx)).feed(fn.arguments)


def _apply_remainders(chunk: Any, remainders: dict[tuple[Any, ...], str]) -> None:
    """Best-effort: append each unmasker's flushed tail to the matching
    position on the final chunk. Only reached when the stream ended
    mid-placeholder."""
    if not remainders:
        return
    choices = getattr(chunk, "choices", None) or []
    by_index = {getattr(c, "index", 0) or 0: c for c in choices}
    fallback = choices[0] if choices else None

    for key, rem in remainders.items():
        choice = by_index.get(key[1], fallback)
        delta = getattr(choice, "delta", None) if choice is not None else None
        if delta is None:
            continue
        if key[0] == "content":
            existing = getattr(delta, "content", None)
            delta.content = (existing + rem) if isinstance(existing, str) else rem
        else:  # tool_args
            for call in getattr(delta, "tool_calls", None) or []:
                fn = getattr(call, "function", None)
                if (getattr(call, "index", 0) or 0) == key[2] and fn is not None:
                    fn.arguments = (getattr(fn, "arguments", "") or "") + rem


async def unmask_stream(session: Session, source: AsyncIterator[Any]) -> AsyncIterator[Any]:
    unmaskers = _Unmaskers(session.mapping)
    prev: Any = _MISSING
    async for chunk in source:
        _feed_chunk(chunk, unmaskers)
        if prev is not _MISSING:
            yield prev
        prev = chunk
    if prev is not _MISSING:
        _apply_remainders(prev, unmaskers.flush_remainders())
        yield prev
