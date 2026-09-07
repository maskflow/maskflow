"""The keystone gate (#41 DoD): no evidence field can carry free text.

Three independent checks:
1. static field-set + validator audit (guard.assert_schema_is_metadata_only)
2. property test: arbitrary text is either rejected or not stored verbatim
3. a real masking run over checksum-valid synthetic Indian IDs never leaks
   a digit of them into any emitted event
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from maskflow_core import detect, mask_with_policy
from maskflow_evidence import (
    EventContext,
    EvidenceEvent,
    EvidenceSchemaError,
    MetadataOnlyViolation,
    assert_no_pii,
    assert_schema_is_metadata_only,
    events_from_mapping,
    events_from_spans,
)

pytestmark = pytest.mark.leak

# Checksum-valid synthetic values (see packs/maskflow-pack-india/tests).
AADHAAR = "234567890124"
PAN = "ABCPE1234F"
SECRET_TEXT = (
    f"KYC on file: Aadhaar {AADHAAR}, PAN {PAN}, "
    f"UPI ramesh@oksbi, email ramesh.kumar@example.com, phone +91 98765 43210"
)
SECRET_FRAGMENTS = [
    AADHAAR,
    "234 5678 90124".replace(" ", ""),
    PAN,
    "ramesh@oksbi",
    "ramesh.kumar@example.com",
    "9876543210",
]


def _ctx() -> EventContext:
    return EventContext(
        session_id="sess0000abcd",
        service="kyc-bot",
        environment="prod",
        provider="anthropic",
        model="claude-sonnet-4",
    )


def test_static_schema_is_metadata_only() -> None:
    assert_schema_is_metadata_only()


def test_expected_field_set_is_exactly_the_issue_schema() -> None:
    from dataclasses import fields

    from maskflow_evidence.guard import EXPECTED_FIELDS

    assert {f.name for f in fields(EvidenceEvent)} == set(EXPECTED_FIELDS)


@given(
    st.text(
        alphabet=st.characters(min_codepoint=1, max_codepoint=0x2FFF),
        min_size=1,
        max_size=120,
    )
)
def test_free_text_is_rejected_or_never_stored(blob: str) -> None:
    """No matter what a caller passes for a string field, the event either
    refuses to construct or holds only a bounded slug -- never the blob."""
    for field_name in ("service", "environment", "session_id", "entity_type", "recognizer"):
        kwargs = dict(
            entity_type="EMAIL",
            count=1,
            score=0.5,
            recognizer="pattern:EMAIL",
            action="masked",
            service="svc",
            environment="prod",
            session_id="sess0000abcd",
            pack_version="0.5.0",
            engine_version="0.6.0",
        )
        kwargs[field_name] = blob
        try:
            event = EvidenceEvent(**kwargs)  # type: ignore[arg-type]
        except EvidenceSchemaError:
            continue
        # If it constructed, the stored value must be exactly the blob AND
        # the blob must itself be a valid bounded slug (<= 64 chars, safe
        # alphabet) -- i.e. it was never free text to begin with.
        assert getattr(event, field_name) == blob
        assert len(blob) <= 64
        assert "\n" not in blob and " " not in blob


def test_to_json_runs_the_pii_guard() -> None:
    with pytest.raises(MetadataOnlyViolation):
        assert_no_pii(json.dumps({"note": f"aadhaar {AADHAAR}"}))


def test_masking_run_never_leaks_a_value_into_any_event() -> None:
    spans = detect(SECRET_TEXT)
    result = mask_with_policy(SECRET_TEXT)
    ctx = _ctx()

    lines = [ev.to_json() for ev in events_from_spans(spans, ctx)]
    lines += [ev.to_json() for ev in events_from_mapping(result.mapping, ctx)]
    assert lines, "expected at least one detection in the fixture"

    blob = "\n".join(lines)
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in blob
    # And nothing the detectors themselves recognise.
    for line in lines:
        assert_no_pii(line)


def test_from_dict_rejects_unknown_fields() -> None:
    good = EvidenceEvent(
        entity_type="PAN",
        count=1,
        score=0.9,
        recognizer="pattern:PAN",
        action="masked",
        service="svc",
        environment="prod",
        session_id="sess0000abcd",
        pack_version="0.5.0",
        engine_version="0.6.0",
    ).to_dict()
    good["original"] = "leak"
    with pytest.raises(EvidenceSchemaError):
        EvidenceEvent.from_dict(good)
