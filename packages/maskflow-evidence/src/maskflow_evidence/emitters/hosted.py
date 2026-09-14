"""Batch events and POST them to MaskFlow's hosted collector (Evidence Cloud).

Requires the ``hosted`` extra (``pip install maskflow-evidence[hosted]``)
for ``httpx``. Same shape as :class:`~maskflow_evidence.emitters.webhook.WebhookEmitter`
-- synchronous, tight-timeout, wrapped by :class:`~maskflow_evidence.emitters.SafeEmitter`
so a collector outage never blocks the masking path -- with two differences
the paid multi-tenant collector needs: events are batched client-side
(never one HTTP request per event) before being sent, and a transient
failure is retried a bounded number of times with backoff before the batch
is dropped.

This is a transport, not a gate: sending events here is exactly as optional
as every other sink, requires an explicit opt-in ``api_key``, and carries
the same metadata-only event shape as every other emitter (see
``../schema.py``). The collector re-validates that shape server-side using
the same ``EvidenceEvent`` this client already validated against -- it is
never simply trusted from the client.

Trade-off worth knowing: because ``emit`` is synchronous like every other
sink here, a retry only happens on the one call that fills the batch --
worst case that call blocks for roughly ``max_retries`` timeouts plus
backoff (defaults: ~2 * 2s + ~1.5s), not every call. A background-thread
design would smooth that out but no other sink in this package uses one;
matching the existing synchronous style keeps the failure mode uniform and
easy to reason about.
"""

from __future__ import annotations

import time

from ..schema import EvidenceEvent

# The default collector endpoint. Overridable via [evidence] url for a
# staging collector or (self-hosters who want the *shape* of this sink
# without the paid service) a compatible endpoint of their own.
DEFAULT_URL = "https://collect.maskflow.in/v1/ingest"


class HostedEmitter:
    def __init__(
        self,
        api_key: str,
        *,
        url: str = DEFAULT_URL,
        batch_size: int = 20,
        timeout: float = 2.0,
        max_retries: int = 2,
        backoff: float = 0.5,
    ) -> None:
        if not api_key:
            raise ValueError("hosted sink requires [evidence] api_key")
        if not url:
            raise ValueError("hosted sink requires a non-empty url")
        if batch_size < 1:
            raise ValueError("hosted sink batch_size must be >= 1")
        try:
            import httpx
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise ModuleNotFoundError(
                "the hosted evidence sink needs httpx -- install maskflow-evidence[hosted]"
            ) from exc
        self._url = url
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._backoff = backoff
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
        )
        self._buffer: list[EvidenceEvent] = []

    def emit(self, event: EvidenceEvent) -> None:
        self._buffer.append(event)
        if len(self._buffer) >= self._batch_size:
            self._flush()

    def close(self) -> None:
        try:
            if self._buffer:
                self._flush()
        finally:
            self._client.close()

    def _flush(self) -> None:
        import httpx

        # Pulled out before the request so a failed send never leaves a
        # stale batch sitting in the buffer to be resent (and duplicated)
        # alongside whatever accumulates next.
        batch, self._buffer = self._buffer, []
        if not batch:
            return
        payload = {"events": [event.to_dict() for event in batch]}

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(self._url, json=payload)
                response.raise_for_status()
                return
            except httpx.HTTPStatusError as exc:
                # A 4xx means the request itself is wrong (bad api_key,
                # malformed payload) -- retrying won't help, fail fast.
                if exc.response.status_code < 500 or attempt == self._max_retries:
                    raise
            except httpx.TransportError:
                if attempt == self._max_retries:
                    raise
            time.sleep(self._backoff * (2**attempt))
