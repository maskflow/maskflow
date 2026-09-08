"""MaskFlow evidence layer.

A metadata-only, verifiable record of *what was masked* -- never the values.
See ``docs/evidence.md`` for the schema, what is deliberately not collected,
and the self-hosted setup guide.

Off by default: nothing is emitted unless ``[evidence] enabled = true`` (or
the equivalent env var) selects a sink.
"""

from __future__ import annotations

from .config import EvidenceConfig
from .derive import (
    EventContext,
    action_for_strategy,
    events_from_mapping,
    events_from_spans,
)
from .emitters import Emitter, NullEmitter, SafeEmitter, build_emitter
from .guard import (
    MetadataOnlyViolation,
    assert_no_pii,
    assert_schema_is_metadata_only,
    scan_for_pii,
)
from .schema import ACTIONS, EvidenceEvent, EvidenceSchemaError
from .versions import engine_version, pack_version, pack_versions

__all__ = [
    "ACTIONS",
    "EvidenceConfig",
    "EvidenceEvent",
    "EvidenceSchemaError",
    "EventContext",
    "Emitter",
    "NullEmitter",
    "SafeEmitter",
    "MetadataOnlyViolation",
    "action_for_strategy",
    "assert_no_pii",
    "assert_schema_is_metadata_only",
    "build_emitter",
    "events_from_mapping",
    "events_from_spans",
    "engine_version",
    "pack_version",
    "pack_versions",
    "scan_for_pii",
]
