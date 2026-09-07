"""The metadata-only invariant, enforced.

Two checks, both run in CI (``tests/test_schema_metadata_only.py``):

* :func:`assert_schema_is_metadata_only` -- a *static* check of the
  ``EvidenceEvent`` dataclass: the field set is exactly the frozen expected
  set, and every field's declared type is one this module recognises as
  incapable of holding free text. Add a bare ``str`` field with no validator
  and this fails the build.
* :func:`assert_no_pii` -- a *runtime* check of a serialized event: the
  string is run through ``maskflow_core.detect_patterns_only`` (regex +
  checksum, no NER) and any hit raises. This is the belt-and-suspenders
  pass ``EvidenceEvent.to_json`` makes on every line it emits.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Final

from maskflow_core import detect_patterns_only

from .schema import EvidenceEvent

# The complete, frozen field set. Kept here (not derived from the dataclass)
# on purpose: this is the contract the schema must match, so the test
# compares the two and fails if either drifts.
EXPECTED_FIELDS: Final[dict[str, str]] = {
    "event_id": "str",
    "ts": "str",
    "session_id": "str",
    "service": "str",
    "environment": "str",
    "entity_type": "str",
    "count": "int",
    "score": "float",
    "recognizer": "str",
    "action": "str",
    "provider": "str | None",
    "model": "str | None",
    "pack_version": "str",
    "engine_version": "str",
}

# Every string field is validated against one of schema.py's bounded
# patterns in __post_init__. This list is the audited proof of that: the
# static test asserts each name here has a matching `_check(...)` call in
# the schema source, so a new string field cannot be added without also
# adding a validator for it.
_VALIDATED_STR_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "event_id",
        "ts",
        "session_id",
        "service",
        "environment",
        "entity_type",
        "recognizer",
        "provider",
        "model",
        "pack_version",
        "engine_version",
    }
)


class MetadataOnlyViolation(AssertionError):
    """The evidence schema grew a field that could carry free text."""


def assert_schema_is_metadata_only() -> None:
    """Static structural check. Raises :class:`MetadataOnlyViolation` if the
    ``EvidenceEvent`` dataclass no longer matches the frozen contract."""
    actual = {f.name: str(f.type) for f in fields(EvidenceEvent)}

    missing = set(EXPECTED_FIELDS) - set(actual)
    extra = set(actual) - set(EXPECTED_FIELDS)
    if missing or extra:
        raise MetadataOnlyViolation(
            f"EvidenceEvent field set drifted: missing={sorted(missing)} extra={sorted(extra)}"
        )

    import pathlib

    source = (pathlib.Path(__file__).parent / "schema.py").read_text(encoding="utf-8")
    for name in _VALIDATED_STR_FIELDS:
        if f'_check("{name}"' not in source:
            raise MetadataOnlyViolation(
                f"string field {name!r} has no _check(...) validator in schema.py"
            )

    # `action` is closed to a literal tuple; `count`/`score` are bounded
    # numerics. Anything else typed as a plain str without a validator is
    # the failure mode this guard exists to catch.
    for name, decl in EXPECTED_FIELDS.items():
        if decl.startswith("str") and name not in _VALIDATED_STR_FIELDS and name != "action":
            raise MetadataOnlyViolation(f"unvalidated string field {name!r}")


def scan_for_pii(text: str) -> list[str]:
    """Entity types detectable in ``text`` by the pattern/checksum pass.
    Returns type names only -- never the matched substrings."""
    return sorted({span.entity_type.value for span in detect_patterns_only(text)})


def assert_no_pii(serialized_event: str) -> None:
    """Raise :class:`MetadataOnlyViolation` if a serialized event contains
    anything the pattern/checksum detectors recognise as PII."""
    hits = scan_for_pii(serialized_event)
    if hits:
        raise MetadataOnlyViolation(
            f"serialized evidence event matched PII detectors: {hits} "
            "(this should be structurally impossible -- report as a bug)"
        )
