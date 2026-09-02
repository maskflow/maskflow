"""postgres source: run a user SELECT over a server-side cursor and scan
named text columns. Requires the [postgres] extra
(`pip install maskflow-cli[postgres]`).

The query MUST be deterministically ordered (ORDER BY a stable key) --
resume replays from a row OFFSET, so an unstable order would skip or
double-count rows on resume.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, ClassVar

from ..spec import SourceSpec
from ._files import resolve_columns
from ._meta import parse_timestamp
from .base import Preflight, ScanRecord, Source, SourceConfigError, SourceEstimate

_ITERSIZE = 1000


def _psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise SourceConfigError(
            "postgres source needs the [postgres] extra: pip install 'maskflow-cli[postgres]'"
        ) from exc
    return psycopg


class PostgresSource:
    name: ClassVar[str] = "postgres"

    def __init__(
        self, conninfo: str, query: str, columns: tuple[str, ...], spec: SourceSpec
    ) -> None:
        self._conninfo = conninfo
        self._query = query.rstrip().rstrip(";")
        self._columns = columns
        self._spec = spec
        # --timestamp-field / --provider-field / --service-field name result
        # columns here (or spec.extra.*_column as an alias).
        self._ts_col = spec.timestamp_field or spec.extra.get("timestamp_column")
        self._provider_col = spec.provider_field or spec.extra.get("provider_column")
        self._service_col = spec.service_field or spec.extra.get("service_column")

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        conninfo = spec.target or os.environ.get("DATABASE_URL") or ""
        if not conninfo:
            raise SourceConfigError(
                "postgres source needs a connection string (argument or $DATABASE_URL)"
            )
        if not spec.query:
            raise SourceConfigError(
                "postgres source needs --query 'SELECT ... FROM ... ORDER BY <key>'"
            )
        if "order by" not in spec.query.lower():
            raise SourceConfigError("--query must contain an ORDER BY for a resumable scan")
        columns = resolve_columns(spec.columns)
        return cls(conninfo, spec.query, columns, spec)

    def preflight(self) -> Preflight:
        try:
            with _psycopg().connect(self._conninfo) as conn, conn.cursor() as cur:
                cur.execute(f"SELECT * FROM ({self._query}) AS _mf_scan LIMIT 0")
                names = {d.name for d in (cur.description or [])}
        except Exception as exc:  # noqa: BLE001
            return Preflight(False, f"cannot run query: {exc}")
        missing = [c for c in self._columns if c not in names]
        if missing:
            return Preflight(False, f"columns not in query result: {', '.join(missing)}")
        return Preflight(True)

    def estimate(self) -> SourceEstimate:
        try:
            with _psycopg().connect(self._conninfo) as conn, conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM ({self._query}) AS _mf_scan")
                row = cur.fetchone()
                return SourceEstimate(total_records=int(row[0]) if row else None)
        except Exception:  # noqa: BLE001
            return SourceEstimate()

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        offset = int(resume_cursor) if resume_cursor else 0
        psycopg = _psycopg()
        sql = f"SELECT * FROM ({self._query}) AS _mf_scan OFFSET {offset}"
        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor(name="mf_scan") as cur:
                cur.itersize = _ITERSIZE
                cur.execute(sql)
                columns = [d.name for d in (cur.description or [])]
                idx = {name: i for i, name in enumerate(columns)}
                row_index = offset
                for row in cur:
                    row_index += 1
                    provider = _cell(row, idx, self._provider_col) or self._spec.provider
                    service = _cell(row, idx, self._service_col)
                    timestamp = parse_timestamp(_cell(row, idx, self._ts_col))
                    for sub, col in enumerate(self._columns):
                        value = row[idx[col]] if col in idx else None
                        if not isinstance(value, str) or not value:
                            continue
                        yield ScanRecord(
                            id=f"{row_index}:{sub}",
                            text=value,
                            provider=provider,
                            service=service,
                            timestamp=timestamp,
                            record_ref=f"pg row {row_index}:{col}",
                        )

    def cursor_after(self, record: ScanRecord) -> str:
        return record.id.split(":")[0]


def _cell(row: tuple[Any, ...], idx: dict[str, int], col: str | None) -> str | None:
    if not col or col not in idx:
        return None
    value = row[idx[col]]
    return value if isinstance(value, str) else (str(value) if value is not None else None)
