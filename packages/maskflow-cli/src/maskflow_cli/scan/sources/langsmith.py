"""langsmith source: reads LLM runs from the LangSmith API. Credentials
from $LANGSMITH_API_KEY, endpoint from $LANGSMITH_ENDPOINT (default
api.smith.langchain.com).

Outbound requests read *your* LangSmith data; nothing is transmitted --
see docs/scan.md.
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

_DEFAULT_ENDPOINT = "https://api.smith.langchain.com"
_PAGE_LIMIT = 100


class LangsmithSource:
    name: ClassVar[str] = "langsmith"

    def __init__(self, endpoint: str, api_key: str, spec: SourceSpec) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._spec = spec

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
        if not key:
            raise SourceAuthError("langsmith source needs $LANGSMITH_API_KEY")
        endpoint = (
            spec.target
            or os.environ.get("LANGSMITH_ENDPOINT")
            or os.environ.get("LANGCHAIN_ENDPOINT")
            or _DEFAULT_ENDPOINT
        )
        return cls(endpoint, key, spec)

    def _reader(self) -> HttpReader:
        return HttpReader(self._endpoint, {"x-api-key": self._api_key})

    def preflight(self) -> Preflight:
        try:
            with self._reader() as r:
                r.request("POST", "/runs/query", json={"limit": 1, "run_type": "llm"})
        except SourceAuthError as exc:
            return Preflight(False, str(exc))
        except Exception as exc:  # noqa: BLE001
            return Preflight(False, f"cannot reach {self._endpoint}: {exc}")
        return Preflight(True)

    def estimate(self) -> SourceEstimate:
        return SourceEstimate()

    def _body(self, cursor: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {"limit": _PAGE_LIMIT, "run_type": "llm", "is_root": True}
        if cursor:
            body["cursor"] = cursor
        if self._spec.since:
            body["start_time"] = self._spec.since.isoformat()
        if self._spec.until:
            body["end_time"] = self._spec.until.isoformat()
        return body

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        cursor = resume_cursor or None
        seen = 0
        with self._reader() as reader:
            while True:
                body = reader.request("POST", "/runs/query", json=self._body(cursor))
                runs = body.get("runs") or body.get("data") or []
                for run in runs:
                    yield from self._rows(run, seen)
                    seen += 1
                cursor = (body.get("cursors") or {}).get("next")
                if not runs or not cursor:
                    return

    def _rows(self, run: dict[str, Any], index: int) -> Iterator[ScanRecord]:
        run_id = str(run.get("id", index))
        model = ((run.get("extra") or {}).get("metadata") or {}).get("ls_model_name") or run.get(
            "name"
        )
        ts = parse_timestamp(run.get("start_time"))
        pairs = [
            *messages_from(run.get("inputs"), default_role="user"),
            *messages_from(run.get("outputs"), default_role="assistant"),
        ]
        for sub, (role, text) in enumerate(pairs):
            yield ScanRecord(
                id=f"{run_id}:{sub}",
                text=text,
                provider="langsmith",
                service=str(model) if model else None,
                timestamp=ts,
                role=role,
                record_ref=f"langsmith run {run_id}",
            )

    def cursor_after(self, record: ScanRecord) -> str:
        # Cursor-paginated: the checkpoint stores the last page cursor, set
        # by the pipeline from the raw response, not derivable from a single
        # record. We return the run id; pipeline treats an unchanged cursor
        # as "restart this page", which re-scans <=100 runs on resume.
        return record.id.split(":")[0]
