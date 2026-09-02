"""Source registry: name -> Source class. `get_source(spec)` builds the
one the CLI selected."""

from __future__ import annotations

from ..spec import SourceSpec
from .base import (
    Preflight,
    ScanRecord,
    Source,
    SourceAuthError,
    SourceConfigError,
    SourceError,
    SourceEstimate,
)
from .csv import CsvSource
from .dir import DirSource
from .helicone import HeliconeSource
from .jsonl import JsonlSource
from .langfuse import LangfuseSource
from .langsmith import LangsmithSource
from .postgres import PostgresSource
from .s3 import S3Source

SOURCES: dict[str, type[Source]] = {
    "jsonl": JsonlSource,
    "ndjson": JsonlSource,
    "csv": CsvSource,
    "dir": DirSource,
    "s3": S3Source,
    "postgres": PostgresSource,
    "langfuse": LangfuseSource,
    "helicone": HeliconeSource,
    "langsmith": LangsmithSource,
}

SOURCE_NAMES = tuple(SOURCES)


def get_source(spec: SourceSpec) -> Source:
    try:
        cls = SOURCES[spec.kind]
    except KeyError:
        raise SourceConfigError(
            f"unknown source {spec.kind!r}; choose one of: {', '.join(SOURCES)}"
        ) from None
    return cls.from_spec(spec)


__all__ = [
    "SOURCES",
    "SOURCE_NAMES",
    "get_source",
    "Source",
    "ScanRecord",
    "Preflight",
    "SourceEstimate",
    "SourceError",
    "SourceConfigError",
    "SourceAuthError",
]
