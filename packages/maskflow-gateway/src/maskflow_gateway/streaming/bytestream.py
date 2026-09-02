"""Byte-level wrapper around :class:`StreamingUnmasker`.

The upstream stream is UTF-8 bytes, and a chunk boundary can fall in the
middle of a multi-byte code point. An incremental decoder holds the
incomplete trailing bytes until the rest arrives, so the trie layer above
only ever sees whole code points. Placeholders are ASCII, so they are
never affected; original values may be any Unicode but are only ever
emitted, never scanned.
"""

from __future__ import annotations

import codecs
from collections.abc import Mapping as MappingABC

from maskflow_core import Mapping

from .unmask import StreamingUnmasker


class ByteStreamingUnmasker:
    """Feed ``bytes`` in, get unmasked ``str`` out. One per streamed
    response."""

    def __init__(self, mapping: MappingABC[str, object] | Mapping) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._inner = StreamingUnmasker(mapping)

    def feed(self, chunk: bytes) -> str:
        # decode() buffers an incomplete trailing multi-byte sequence and
        # returns "" for it until the continuation bytes arrive.
        return self._inner.feed(self._decoder.decode(chunk))

    def flush(self) -> str:
        # final=True raises UnicodeDecodeError if the stream ended on a
        # truncated code point -- a genuinely broken upstream response, which
        # the caller surfaces as a 502.
        tail = self._decoder.decode(b"", final=True)
        return self._inner.feed(tail) + self._inner.flush()

    @property
    def pending(self) -> str:
        return self._inner.pending
