"""helicone source: reads logged requests from the Helicone API.
Credentials from $HELICONE_API_KEY.

Outbound requests go to *your* Helicone account to read *your* data; no
scan data is transmitted -- see docs/scan.md.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, ClassVar

from ..spec import SourceSpec
from ._api_common import messages_from
from ._http import HttpReader
from ._meta import parse_timestamp
from .base import Preflight, ScanRecord, Source, SourceAuthError, SourceEstimate

_HOST = "https://api.helicone.ai"
_PAGE_LIMIT = 100


class HeliconeSource:
    name: ClassVar[str] = "helicone"

    def __init__(self, api_key: str, spec: SourceSpec) -> None:
        self._api_key = api_key
        self._spec = spec

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        key = os.environ.get("HELICONE_API_KEY")
        if not key:
            raise SourceAuthError("helicone source needs $HELICONE_API_KEY")
        return cls(key, spec)

    def _reader(self) -> HttpReader:
        return HttpReader(_HOST, {"Authorization": f"Bearer {self._api_key}"})

    def preflight(self) -> Preflight:
        try:
            with self._reader() as r:
                r.request("POST", "/v1/request/query", json={"limit": 1, "offset": 0})
        except SourceAuthError as exc:
            return Preflight(False, str(exc))
        except Exception as exc:  # noqa: BLE001
            return Preflight(False, f"cannot reach {_HOST}: {exc}")
        return Preflight(True)

    def estimate(self) -> SourceEstimate:
        return SourceEstimate()

    def _filter(self) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = []
        if self._spec.since:
            clauses.append({"request": {"created_at": {"gte": self._spec.since.isoformat()}}})
        if self._spec.until:
            clauses.append({"request": {"created_at": {"lte": self._spec.until.isoformat()}}})
        if not clauses:
            return {}
        return clauses[0] if len(clauses) == 1 else {"and": clauses}

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        offset = int(resume_cursor) if resume_cursor else 0
        with self._reader() as reader:
            while True:
                body = reader.request(
                    "POST",
                    "/v1/request/query",
                    json={"filter": self._filter(), "limit": _PAGE_LIMIT, "offset": offset},
                )
                rows = body.get("data") or []
                for i, row in enumerate(rows):
                    yield from self._rows(row, offset + i)
                if len(rows) < _PAGE_LIMIT:
                    return
                offset += len(rows)

    def _rows(self, row: dict[str, Any], index: int) -> Iterator[ScanRecord]:
        model = row.get("request_model") or row.get("model")
        ts = parse_timestamp(row.get("request_created_at") or row.get("created_at"))
        rid = str(row.get("request_id") or row.get("id") or index)
        pairs = [
            *messages_from(row.get("request_body"), default_role="user"),
            *messages_from(row.get("response_body"), default_role="assistant"),
        ]
        for sub, (role, text) in enumerate(pairs):
            yield ScanRecord(
                id=f"{index}:{sub}",
                text=text,
                provider="helicone",
                service=str(model) if model else None,
                timestamp=ts,
                role=role,
                record_ref=f"helicone request {rid}",
            )

    def cursor_after(self, record: ScanRecord) -> str:
        return record.id.split(":")[0]
