"""A small HTTP helper for the API-backed sources (langfuse / helicone /
langsmith). Deliberately not a vendor SDK -- one dependency (`httpx`), one
retry/backoff policy, one place that knows we only ever GET/POST-to-read.
"""

from __future__ import annotations

import time
from typing import Any

from .base import SourceAuthError, SourceError

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 4
_TIMEOUT_S = 30.0


def _client() -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - httpx is a base dep
        raise SourceError("the API sources need httpx (pip install maskflow-cli)") from exc
    return httpx


class HttpReader:
    """One configured, connection-pooled session against a single API host."""

    def __init__(self, base_url: str, headers: dict[str, str]) -> None:
        httpx = _client()
        self._session = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=_TIMEOUT_S,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> HttpReader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            resp = self._session.request(method, path, params=params, json=json)
            if resp.status_code == 401 or resp.status_code == 403:
                raise SourceAuthError(
                    f"{resp.status_code} from {path} -- check the API key / permissions"
                )
            if resp.status_code in _RETRY_STATUS:
                last_exc = SourceError(f"{resp.status_code} from {path}")
                time.sleep(min(2**attempt, 8))
                continue
            if resp.status_code >= 400:
                # Body may echo a query term; surface status + path only.
                raise SourceError(f"{resp.status_code} from {path}")
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}
        assert last_exc is not None
        raise last_exc
