"""The PII-free report data model.

`json_out.py` -- and, from M3, `html.py` -- render from an `AuditSummary`
and nothing else. So "does the audit report leak PII?" reduces to "is every
string on this object PII-free?", which the leak gate checks by running a
full audit over a tree seeded with canary values and asserting none of them
appears in any rendered format. That is the same argument, and the same
guarantee, as maskflow-cli's scan report.

What is on this object, deliberately: file paths, function names, dotted
call paths, sink ids, provider and host names, column and field *names*,
argument names, and counts. What is never on it: source text, string
literal contents, the values in a database, or a canary value.

Unlike `ScanSummary`, this model carries an explicit `schema_version`. The
CI baseline diff must be able to refuse a file it does not understand, and
the evidence product consumes this format -- both need a version they can
check rather than infer. The convention is maskflow-attest's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

#: Bump on any change that an existing consumer could not read. Additive
#: fields do not need a bump; renaming, removing, or re-meaning one does.
AUDIT_SCHEMA_VERSION: Final = "1"

#: Canary state per flow. M1 never runs canaries, so every flow reports
#: `not_run` -- the field exists now so the schema does not change shape
#: when M2 starts filling it.
CANARY_NOT_RUN = "not_run"
CANARY_ESCAPED = "escaped"
CANARY_CONTAINED = "contained"
CANARY_NOT_EXERCISED = "not_exercised"

CANARY_STATUSES: tuple[str, ...] = (
    CANARY_NOT_RUN,
    CANARY_ESCAPED,
    CANARY_CONTAINED,
    CANARY_NOT_EXERCISED,
)


@dataclass(frozen=True)
class AuditScope:
    """What was examined."""

    root: str  # the path as given, never expanded to a home directory
    files_examined: int
    files_skipped: int
    languages: tuple[str, ...]  # ("python",) in v1
    canaries_run: bool
    generated_at: datetime


@dataclass(frozen=True)
class SourceRow:
    """One traced origin of a flow's payload. Identifiers only."""

    kind: str
    detail: str
    predicted_entity_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanaryEscapeRow:
    """One canary observed leaving, as the report presents it.

    The entity TYPE and the form it was found in -- never the value. A
    report that named the canary value would be a report carrying an
    identifier-shaped string, and a reader could not tell it from a real one.
    """

    entity_type: str
    form: str  # raw | normalised | base64 | digit-run
    host: str
    path: str
    library: str
    app_stack: tuple[str, ...]


@dataclass(frozen=True)
class CanaryRun:
    """What the canary run did. Seeds and counts, never values."""

    seed: int
    identities: int
    entity_types: tuple[str, ...]
    command: tuple[str, ...]
    command_exit_code: int
    requests_intercepted: int
    escapes_observed: int
    unattributed_escapes: int
    seeded_targets: tuple[str, ...]
    warnings: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class FlowRow:
    """One egress call site, as the report presents it."""

    flow_id: str
    file: str
    line: int
    function: str
    sink_id: str
    category: str
    provider: str
    host: str
    call_path: str
    masking_status: str
    masking_reason: str
    payload_args: tuple[str, ...]
    sources: tuple[SourceRow, ...]
    confidence: str
    canary_status: str
    canary_escapes: tuple[CanaryEscapeRow, ...]
    explanation: tuple[str, ...]


@dataclass(frozen=True)
class Coverage:
    """The headline numbers."""

    total_flows: int
    masked: int
    unmasked: int
    unknown: int
    confirmed_leaks: int

    @property
    def headline(self) -> str:
        """e.g. "31 of 33 LLM paths masked"."""
        return f"{self.masked} of {self.total_flows} LLM egress paths masked"


@dataclass(frozen=True)
class Breakdown:
    """A counted grouping, same shape as the scan report's."""

    label: str
    count: int


@dataclass(frozen=True)
class SkippedFileRow:
    """A file the walk could not read. Carries a reason, never content."""

    file: str
    reason: str


@dataclass(frozen=True)
class AuditMethodology:
    """How the numbers were produced, so a reader can judge them."""

    detector_versions: dict[str, str]
    registry_version: int
    sinks_known: int
    sink_ids: tuple[str, ...]
    limits_note: str
    not_detected_note: str
    config_fingerprint: str


@dataclass(frozen=True)
class AuditSummary:
    """Everything a renderer may see.

    `schema_version` is first so it is the first key in the JSON, readable
    without parsing the whole document.
    """

    schema_version: str
    scope: AuditScope
    coverage: Coverage
    headline: str
    flows: tuple[FlowRow, ...]
    by_category: tuple[Breakdown, ...]
    by_provider: tuple[Breakdown, ...]
    by_status: tuple[Breakdown, ...]
    skipped_files: tuple[SkippedFileRow, ...]
    canary_run: CanaryRun | None
    methodology: AuditMethodology
    dpdp_appendix_slot: str = field(default="<!-- DPDP_RULE6_APPENDIX -->")
