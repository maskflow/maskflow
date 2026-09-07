"""POST one JSON event per request to a configured URL.

Requires the ``webhook`` extra (``pip install maskflow-evidence[webhook]``)
for ``httpx``. Synchronous and short-timeout by design: an evidence sink
must not add latency or a failure mode to the masking path, so
:class:`~maskflow_evidence.emitters.SafeEmitter` (which wraps this) drops on
any error, and the timeout here is deliberately tight.
"""

from __future__ import annotations

import json

from ..schema import EvidenceEvent


class WebhookEmitter:
    def __init__(self, url: str, *, timeout: float = 2.0) -> None:
        if not url:
            raise ValueError("webhook sink requires [evidence] url")
        try:
            import httpx
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise ModuleNotFoundError(
                "the webhook evidence sink needs httpx -- install maskflow-evidence[webhook]"
            ) from exc
        self._url = url
        self._client = httpx.Client(timeout=timeout)

    def emit(self, event: EvidenceEvent) -> None:
        # to_dict() (not to_json()) so httpx sets Content-Type and we still
        # get the guard pass via json.dumps below.
        payload = event.to_dict()
        body = json.dumps(payload)
        from ..guard import assert_no_pii

        assert_no_pii(body)
        self._client.post(self._url, content=body, headers={"content-type": "application/json"})

    def close(self) -> None:
        self._client.close()
