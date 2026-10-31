"""Metadata-only evidence events for an audit run.

The audit is the pre-incident half of the evidence story: `scan` and the
gateway record that masking *ran*, this records which paths were *capable*
of leaking and which were proven to. Both feed the same emitters, so a
subscriber's export can show the coverage trend over time.

What is emitted: one event per masking status, carrying the flow count.
Plus, when canaries ran, one event per entity type that escaped. That is
all. Never a flow's file path, never a column name, never a canary value --
a path like `billing/kyc_upload.py` is itself information about the
business, and this stream is designed to leave the building.

`maskflow-evidence` is an optional dependency, imported lazily, so the
audit runs identically without it.

The schema has no audit-specific fields, and this module deliberately does
not add any: it maps onto the existing 14-field `EvidenceEvent` by treating
a masking status as the `action` and a flow count as the `count`. Extending
the shared schema for one consumer would make every other consumer's guard
weaker.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from .report.summary import AuditSummary

if TYPE_CHECKING:  # pragma: no cover -- typing only, never imported at runtime
    from maskflow_evidence.schema import EvidenceEvent

_MISSING = (
    "--evidence needs the evidence extra -- install it with:  "
    "pip install 'maskflow-audit[evidence]'"
)

#: Masking status -> the evidence schema's `action` vocabulary. The schema
#: allows exactly ("masked", "redacted", "surrogate", "passed"), and we do
#: not get to invent a fifth: an unmasked or unknown egress path is one
#: where personal data would have `passed` through unprotected.
_ACTION_FOR_STATUS: dict[str, str] = {
    "masked_via_mask_call": "masked",
    "masked_via_gateway_base_url": "masked",
    "masked_via_integration": "masked",
    "unmasked": "passed",
    "unknown": "passed",
}

#: A synthetic entity type naming what the event counts. The schema
#: validates this as a slug, so these read as entity types to any
#: consumer -- which is why they are prefixed, not disguised.
_FLOW_ENTITY = "AUDIT_FLOW"
_LEAK_ENTITY = "AUDIT_CONFIRMED_LEAK"


class EvidenceExtraMissing(RuntimeError):
    """Raised when --evidence is requested but maskflow-evidence is absent."""

    def __init__(self) -> None:
        super().__init__(_MISSING)


def build_events(
    summary: AuditSummary,
    *,
    service: str = "maskflow_audit",
    environment: str = "local",
) -> list[EvidenceEvent]:
    """One event per masking status, plus one per escaped entity type."""
    try:
        from maskflow_evidence.derive import EventContext
        from maskflow_evidence.schema import EvidenceEvent
    except ModuleNotFoundError as exc:  # pragma: no cover -- extra absent
        raise EvidenceExtraMissing() from exc

    versions = summary.methodology.detector_versions
    context = EventContext(
        session_id="audit_" + secrets.token_hex(8),
        service=service,
        environment=environment,
    )

    events: list[EvidenceEvent] = []
    for row in summary.by_status:
        action = _ACTION_FOR_STATUS.get(row.label)
        if action is None or row.count < 1:
            continue
        events.append(
            EvidenceEvent(
                entity_type=_FLOW_ENTITY,
                count=row.count,
                # Not a detection confidence: an audit counts paths, not
                # matches. Pinned at 1.0 so a consumer averaging scores is
                # not skewed by a field that has no meaning here.
                score=1.0,
                recognizer=f"audit:{row.label}",
                action=action,
                service=context.service,
                environment=context.environment,
                session_id=context.session_id,
                pack_version=versions.get("maskflow-pack-india", "0.0.0"),
                engine_version=versions.get("maskflow-core", "0.0.0"),
            )
        )

    escaped: dict[str, int] = {}
    for flow in summary.flows:
        for escape in flow.canary_escapes:
            escaped[escape.entity_type] = escaped.get(escape.entity_type, 0) + 1
    for entity_type, count in sorted(escaped.items()):
        events.append(
            EvidenceEvent(
                entity_type=_LEAK_ENTITY,
                count=count,
                score=1.0,
                # The entity type that escaped travels in the recognizer
                # field, which the schema validates as a slug with one
                # colon -- so a consumer can group by it without the
                # schema needing a new field.
                recognizer=f"canary:{entity_type}",
                action="passed",
                service=context.service,
                environment=context.environment,
                session_id=context.session_id,
                pack_version=versions.get("maskflow-pack-india", "0.0.0"),
                engine_version=versions.get("maskflow-core", "0.0.0"),
            )
        )
    return events


def emit_audit_evidence(
    summary: AuditSummary,
    *,
    enabled: bool,
    service: str = "maskflow_audit",
    environment: str = "local",
) -> int:
    """Emit the events through the configured sink. Returns the count."""
    if not enabled:
        return 0
    try:
        from maskflow_evidence.config import EvidenceConfig
        from maskflow_evidence.emitters import build_emitter
    except ModuleNotFoundError as exc:
        raise EvidenceExtraMissing() from exc

    events = build_events(summary, service=service, environment=environment)
    config = EvidenceConfig.from_env("MASKFLOW_AUDIT_EVIDENCE_")
    if not config.enabled:
        config = EvidenceConfig(enabled=True, sink=config.sink or "stdout")
    emitter = build_emitter(config)
    try:
        for event in events:
            emitter.emit(event)
    finally:
        emitter.close()
    return len(events)
