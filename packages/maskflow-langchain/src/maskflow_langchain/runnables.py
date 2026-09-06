"""``MaskflowDeanonymizer`` -- a streaming-aware ``Runnable[str, str]`` that
restores originals in an LLM's reply.

``PresidioReversibleAnonymizer`` is used in a chain as
``... | RunnableLambda(anonymizer.deanonymize)``, which only fires once the
full string is assembled -- ``chain.stream()`` yields placeholder tokens
until the very end. ``MaskflowDeanonymizer`` instead runs
``maskflow.streaming.StreamingUnmasker`` over the chunk stream, so a
placeholder split across two chunks is stitched back together and each
chunk is emitted with its originals restored as soon as it is safe to.

Use it in place of the ``RunnableLambda``::

    chain = prompt | llm | StrOutputParser() | anonymizer.deanonymizer

``anonymizer.deanonymize`` (the plain string method) stays available for the
non-streaming path and for full Presidio parity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any

from langchain_core.runnables import Runnable
from maskflow.streaming import StreamingUnmasker

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from .anonymizer import MaskflowReversibleAnonymizer


class MaskflowDeanonymizer(Runnable[str, str]):
    """Restores originals in a (possibly streamed) string using the parent
    anonymizer's current mapping. The mapping is read at call time, so
    ``anonymize`` calls made before the chain runs are all reflected."""

    def __init__(self, anonymizer: MaskflowReversibleAnonymizer) -> None:
        self._anonymizer = anonymizer

    def invoke(self, input: str, config: RunnableConfig | None = None, **kwargs: Any) -> str:
        u = StreamingUnmasker(self._anonymizer.token_pairs())
        return u.feed(input) + u.flush()

    def transform(
        self,
        input: Iterator[str],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        # Build the unmasker on the first chunk, not now: under a piped
        # chain.stream() the upstream anonymize() has not run yet at the
        # point this generator body starts, so the mapping would be empty.
        u: StreamingUnmasker | None = None
        for chunk in input:
            if u is None:
                u = StreamingUnmasker(self._anonymizer.token_pairs())
            out = u.feed(chunk)
            if out:
                yield out
        if u is not None:
            tail = u.flush()
            if tail:
                yield tail

    def stream(
        self,
        input: str,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        yield from self.transform(iter([input]), config, **kwargs)

    async def atransform(
        self,
        input: AsyncIterator[str],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        u: StreamingUnmasker | None = None
        async for chunk in input:
            if u is None:
                u = StreamingUnmasker(self._anonymizer.token_pairs())
            out = u.feed(chunk)
            if out:
                yield out
        if u is not None:
            tail = u.flush()
            if tail:
                yield tail

    async def astream(
        self,
        input: str,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        async def _one() -> AsyncIterator[str]:
            yield input

        async for out in self.atransform(_one(), config, **kwargs):
            yield out
