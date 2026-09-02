"""s3 source: recurse an s3://bucket/prefix, streaming each object.
Requires the [s3] extra (`pip install maskflow-cli[s3]`); credentials come
from the standard AWS chain (env vars, ~/.aws, instance role).

Resume uses an HTTP Range request per object, so a resumed scan re-downloads
nothing before its cursor. Cursor = "<key>\x1f<byte-offset>".
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, ClassVar

from ..fieldsel import FieldSelector, extract_all
from ..spec import SourceSpec
from ._files import CSV_EXTENSIONS, JSONL_EXTENSIONS, TEXT_EXTENSIONS
from ._meta import row_metadata
from .base import Preflight, ScanRecord, Source, SourceConfigError, SourceEstimate

_SEP = "\x1f"
_JSON_EXT = (*JSONL_EXTENSIONS, ".json")
_RECOGNISED = (*_JSON_EXT, *CSV_EXTENSIONS, *TEXT_EXTENSIONS)


def _boto3() -> Any:
    try:
        import boto3
    except ImportError as exc:
        raise SourceConfigError(
            "s3 source needs the [s3] extra: pip install 'maskflow-cli[s3]'"
        ) from exc
    return boto3


class S3Source:
    name: ClassVar[str] = "s3"

    def __init__(
        self, bucket: str, prefix: str, selectors: tuple[FieldSelector, ...], spec: SourceSpec
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix
        self._selectors = selectors
        self._spec = spec
        self._client = _boto3().client("s3")

    @classmethod
    def from_spec(cls, spec: SourceSpec) -> Source:
        if not spec.target.startswith("s3://"):
            raise SourceConfigError("s3 source target must be s3://bucket/prefix")
        rest = spec.target[len("s3://") :]
        bucket, _, prefix = rest.partition("/")
        if not bucket:
            raise SourceConfigError("s3 source: missing bucket in s3://bucket/prefix")
        selectors = tuple(FieldSelector.parse(f) for f in spec.fields)
        if not selectors:
            raise SourceConfigError("s3 source needs --field, e.g. --field messages[].content")
        return cls(bucket, prefix, selectors, spec)

    def preflight(self) -> Preflight:
        try:
            self._client.list_objects_v2(Bucket=self._bucket, Prefix=self._prefix, MaxKeys=1)
        except Exception as exc:  # noqa: BLE001
            return Preflight(False, f"cannot list s3://{self._bucket}/{self._prefix}: {exc}")
        return Preflight(True)

    def estimate(self) -> SourceEstimate:
        total = 0
        for obj in self._list_objects():
            total += obj["Size"]
        return SourceEstimate(total_bytes=total)

    def _list_objects(self) -> Iterator[dict[str, Any]]:
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[dict[str, Any]] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(_RECOGNISED) and obj["Size"] > 0:
                    keys.append(obj)
        yield from sorted(keys, key=lambda o: o["Key"])

    def records(self, *, resume_cursor: str | None = None) -> Iterator[ScanRecord]:
        resume_key, resume_offset = _split_cursor(resume_cursor)
        for obj in self._list_objects():
            key = obj["Key"]
            if resume_key is not None and key < resume_key:
                continue
            offset0 = resume_offset if key == resume_key else 0
            yield from self._scan_object(key, offset0)

    def _scan_object(self, key: str, offset0: int) -> Iterator[ScanRecord]:
        kwargs: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if offset0:
            kwargs["Range"] = f"bytes={offset0}-"
        body = self._client.get_object(**kwargs)["Body"]
        offset = offset0
        is_json = key.endswith(_JSON_EXT)
        is_text = key.endswith(TEXT_EXTENSIONS)
        for raw in body.iter_lines(keepends=True):
            offset += len(raw)
            stripped = raw.strip()
            if not stripped:
                continue
            if is_json:
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                texts = extract_all(row, self._selectors)
                if not texts:
                    continue
                provider, service, timestamp, role = row_metadata(row, self._spec)
                for sub, text in enumerate(texts):
                    yield ScanRecord(
                        id=f"{key}{_SEP}{offset}:{sub}",
                        text=text,
                        provider=provider or self._spec.provider,
                        service=service,
                        timestamp=timestamp,
                        role=role,
                        record_ref=f"s3://{self._bucket}/{key}@{offset}",
                    )
            elif is_text:
                yield ScanRecord(
                    id=f"{key}{_SEP}{offset}:0",
                    text=raw.decode("utf-8", errors="replace").rstrip("\n"),
                    provider=self._spec.provider,
                    record_ref=f"s3://{self._bucket}/{key}@{offset}",
                )
            # .csv over S3: streamed CSV with embedded newlines is unsafe to
            # split line-wise; documented as unsupported (use `dir` on a
            # synced copy). Skipped silently rather than mis-parsed.

    def cursor_after(self, record: ScanRecord) -> str:
        return record.id.rsplit(":", 1)[0]


def _split_cursor(cursor: str | None) -> tuple[str | None, int]:
    if not cursor:
        return None, 0
    key, _, offset = cursor.rpartition(_SEP)
    return key, int(offset)
