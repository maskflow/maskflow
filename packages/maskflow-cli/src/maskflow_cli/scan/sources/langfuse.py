"""langfuse source: reads GENERATION observations from the Langfuse public
API. Credentials from $LANGFUSE_PUBLIC_KEY / $LANGFUSE_SECRET_KEY, host
from $LANGFUSE_HOST (default cloud.langfuse.com).

This makes outbound requests to *your* Langfuse instance to read *your*
data. No scan data is sent anywhere -- see docs/scan.md.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator
from typing import Any, ClassVar

from ..spec import SourceSpec
from ._api_common import messages_from
from ._http import HttpReader
from ._meta import parse_timestamp
from .base import Preflight, ScanRecord, Source, SourceAuthError, SourceEstimate

_DEFAULT_HOST = "https://cloud.langfuse.com"
_PAGE_LIMIT = 100


class LangfuseSource:
    name: ClassVar[str] = "langfuse"

    def __init__(self, host: str, auth_header: str, spec: SourceSpec) -> None:
        self._host = host
        self._auth_header = auth_header
        self._spec = spec

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        public = os.environ.get("LANGFUSE_PUBLIC_KEY")
        secret = os.environ.get("LANGFUSE_SECRET_KEY")
        if not public or not secret:
            raise SourceAuthError(
                "langfuse source needs $LANGFUSE_PUBLIC_KEY and $LANGFUSE_SECRET_KEY"
            )
        host = spec.target or os.environ.get("LANGFUSE_HOST") or _DEFAULT_HOST
        token = base64.b64encode(f"{public}:{secret}".encode()).decode()
        return cls(host, f"Basic {token}", spec)

    def _reader(self) -> HttpReader:
        return HttpReader(self._host, {"Authorization": self._auth_header})

    def preflight(self) -> Preflight:
        try:
            with self._reader() as r:
                r.request("GET", "/api/public/observations", params={"limit": 1})
        except SourceAuthError as exc:
            return Preflight(False, str(exc))
        except Exception as exc:  # noqa: BLE001
            return Preflight(False, f"cannot reach {self._host}: {exc}")
        return Preflight(True)

    def estimate(self) -> SourceEstimate:
        return SourceEstimate()

    def _params(self, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "limit": _PAGE_LIMIT, "type": "GENERATION"}
        if self._spec.since:
            params["fromStartTime"] = self._spec.since.isoformat()
        if self._spec.until:
            params["toStartTime"] = self._spec.until.isoformat()
        return params

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        start_page = int(resume_cursor.split(":")[0]) if resume_cursor else 1
        with self._reader() as reader:
            page = start_page
            while True:
                body = reader.request("GET", "/api/public/observations", params=self._params(page))
                rows = body.get("data") or []
                for row in rows:
                    yield from self._rows(row, page)
                meta = body.get("meta") or {}
                total_pages = meta.get("totalPages")
                if not rows or (total_pages is not None and page >= total_pages):
                    return
                page += 1

    def _rows(self, obs: dict[str, Any], page: int) -> Iterator[ScanRecord]:
        obs_id = str(obs.get("id", ""))
        model = obs.get("model")
        ts = parse_timestamp(obs.get("startTime"))
        pairs = [
            *((role, text) for role, text in messages_from(obs.get("input"), default_role="user")),
            *(
                (role, text)
                for role, text in messages_from(obs.get("output"), default_role="assistant")
            ),
        ]
        for sub, (role, text) in enumerate(pairs):
            yield ScanRecord(
                id=f"{page}:{obs_id}:{sub}",
                text=text,
                provider="langfuse",
                service=str(model) if model else None,
                timestamp=ts,
                role=role,
                record_ref=f"langfuse observation {obs_id}",
            )

    def cursor_after(self, record: ScanRecord) -> str:
        return record.id.split(":")[0]
