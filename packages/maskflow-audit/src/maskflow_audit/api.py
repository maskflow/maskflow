"""`run_audit()` -- the one entry point maskflow-cli calls.

Everything above it is a pure function of (source tree, sink registry), so
an audit is reproducible: run it twice on an unchanged tree and the only
field that differs is the timestamp. That is a deliberate property, not a
side effect -- `--ci` compares today's report against a committed baseline,
and a gate that flickers is a gate that gets switched off.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from . import __version__
from .discovery.flows import (
    CONFIDENCE_CONFIRMED,
    MASKED_STATUSES,
    UNKNOWN,
    UNMASKED,
    Flow,
)
from .discovery.walk import DEFAULT_EXCLUDES, discover
from .prove import ProveResult
from .report.summary import (
    AUDIT_SCHEMA_VERSION,
    CANARY_CONTAINED,
    CANARY_ESCAPED,
    CANARY_NOT_EXERCISED,
    CANARY_NOT_RUN,
    AuditMethodology,
    AuditScope,
    AuditSummary,
    Breakdown,
    CanaryEscapeRow,
    CanaryRun,
    Coverage,
    FlowRow,
    SkippedFileRow,
    SourceRow,
)
from .sinks.loader import SinkDef, default_registry

_LIMITS_NOTE = (
    "Static discovery over Python source only. A call whose target or URL is built at "
    "runtime cannot be resolved and is reported `unknown` rather than guessed; a "
    "proxy-side guardrail (a LiteLLM guardrail, a gateway fronted by an unrecognised "
    "hostname) is not visible from the call site. Canaries were not run, so no flow in "
    "this report is a confirmed leak -- only a predicted one."
)

_NOT_DETECTED_NOTE = (
    "Not covered in v1: TypeScript/JavaScript, Go, Java and other languages; dynamic "
    "dispatch through a registry or plugin system; egress from a vendored dependency "
    "(excluded directories are skipped by default); and any sink absent from the "
    "registry. A clean report means nothing known was found, not that nothing exists."
)


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "unknown"


def _detector_versions() -> dict[str, str]:
    """Same provenance block the scan report carries, plus this package."""
    versions = {name: _version(name) for name in ("maskflow-core", "maskflow-audit")}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if name and name.startswith("maskflow-pack-"):
            versions[name] = _version(name)
    versions["maskflow-audit (running)"] = __version__
    return versions


def _config_fingerprint(root: Path, sinks: tuple[SinkDef, ...], excludes: frozenset[str]) -> str:
    """Identifies the inputs, so a baseline knows if the rules changed.

    The tree's own path is not in here: the same repository checked out at
    two paths must fingerprint identically, or a CI runner and a laptop
    would never agree.
    """
    blob = "|".join(
        (
            AUDIT_SCHEMA_VERSION,
            ",".join(sorted(s.id for s in sinks)),
            ",".join(sorted(excludes)),
        )
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _canary_state(flow: Flow, prove: ProveResult | None) -> tuple[str, tuple[CanaryEscapeRow, ...]]:
    """This flow's canary verdict.

    Three distinct non-`not_run` answers, and the distinction matters. A
    flow that escaped is proven. A flow the run never reached is
    `not_exercised` -- the audit learned nothing about it, which is NOT the
    same as learning it is safe, and the report must not let anyone read
    it that way. Only a flow the run actually exercised without leaking is
    `contained`.
    """
    if prove is None or not prove.ran:
        return CANARY_NOT_RUN, ()

    escapes = prove.escapes_for(flow.flow_id)
    if escapes:
        rows = tuple(
            CanaryEscapeRow(
                entity_type=e.entity_type,
                form=e.form,
                host=e.host,
                path=e.path,
                library=e.library,
                app_stack=e.app_stack,
            )
            for e in escapes
        )
        return CANARY_ESCAPED, rows

    # We cannot tell "exercised and clean" from "never reached" per flow
    # without instrumenting the flow itself, so the honest default for a
    # flow with no escape is `not_exercised` unless the run intercepted a
    # request attributed to it.
    if flow.flow_id in prove.exercised_flow_ids:
        return CANARY_CONTAINED, ()
    return CANARY_NOT_EXERCISED, ()


def _flow_row(flow: Flow, prove: ProveResult | None = None) -> FlowRow:
    canary_status, canary_escapes = _canary_state(flow, prove)
    return FlowRow(
        flow_id=flow.flow_id,
        file=flow.file,
        line=flow.line,
        function=flow.function,
        sink_id=flow.sink_id,
        category=flow.category,
        provider=flow.provider,
        host=flow.host,
        call_path=flow.call_path,
        masking_status=flow.masking_status,
        masking_reason=flow.masking_reason,
        payload_args=flow.payload_args,
        sources=tuple(
            SourceRow(kind=s.kind, detail=s.detail, predicted_entity_types=s.predicted_entity_types)
            for s in flow.sources
        ),
        # A canary escape is the strongest evidence available, and it
        # outranks whatever the static trace concluded.
        confidence=CONFIDENCE_CONFIRMED if canary_status == CANARY_ESCAPED else flow.confidence,
        canary_status=canary_status,
        canary_escapes=canary_escapes,
        explanation=flow.explanation
        + (
            (
                f"canary {', '.join(sorted({r.entity_type for r in canary_escapes}))} reached "
                f"{canary_escapes[0].host} from this call site",
            )
            if canary_escapes
            else ()
        ),
    )


def _breakdown(counter: Counter[str]) -> tuple[Breakdown, ...]:
    """Counts, highest first then alphabetical, so output is stable."""
    return tuple(
        Breakdown(label=label, count=count)
        for label, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    )


def _canary_run(prove: ProveResult | None) -> CanaryRun | None:
    """The canary block for the report. Seeds and counts, never values."""
    if prove is None:
        return None
    return CanaryRun(
        seed=prove.manifest.seed,
        identities=prove.manifest.identities,
        entity_types=tuple(sorted(prove.manifest.summary())),
        command=prove.command,
        command_exit_code=prove.exit_code,
        requests_intercepted=prove.captures_seen,
        escapes_observed=len(prove.escapes),
        unattributed_escapes=len(prove.unattributed),
        seeded_targets=tuple(target for result in prove.seed_results for target in result.targets),
        warnings=prove.warnings,
        note=prove.note,
    )


def _order_key(row: FlowRow) -> tuple[int, int, str, int]:
    """Confirmed leaks first, then unmasked, then everything else.

    The report's job is to put the worst thing at the top; a reader who
    stops after the first screen should have seen the leaks.
    """
    rank = {CONFIDENCE_CONFIRMED: 0}.get(row.confidence, 1)
    status_rank = {UNMASKED: 0, UNKNOWN: 1}.get(row.masking_status, 2)
    return (rank, status_rank, row.file, row.line)


def build_summary(
    *,
    root: Path,
    flows: tuple[Flow, ...],
    skipped: tuple[tuple[str, str], ...],
    files_examined: int,
    sinks: tuple[SinkDef, ...],
    excludes: frozenset[str],
    generated_at: datetime,
    prove: ProveResult | None = None,
) -> AuditSummary:
    """Assemble the report model from a completed discovery pass."""
    rows = tuple(sorted((_flow_row(f, prove) for f in flows), key=_order_key))

    masked = sum(1 for f in flows if f.masking_status in MASKED_STATUSES)
    unmasked = sum(1 for f in flows if f.masking_status == UNMASKED)
    unknown = sum(1 for f in flows if f.masking_status == UNKNOWN)
    coverage = Coverage(
        total_flows=len(flows),
        masked=masked,
        unmasked=unmasked,
        unknown=unknown,
        # Only an observed escape counts. Asserting a leak without having
        # watched one happen is exactly what this tool exists not to do.
        confirmed_leaks=sum(1 for r in rows if r.canary_status == CANARY_ESCAPED),
    )

    return AuditSummary(
        schema_version=AUDIT_SCHEMA_VERSION,
        scope=AuditScope(
            root=str(root),
            files_examined=files_examined,
            files_skipped=len(skipped),
            languages=("python",),
            canaries_run=prove is not None and prove.ran,
            generated_at=generated_at,
        ),
        coverage=coverage,
        headline=coverage.headline,
        flows=rows,
        by_category=_breakdown(Counter(f.category for f in flows)),
        by_provider=_breakdown(Counter(f.provider for f in flows)),
        by_status=_breakdown(Counter(f.masking_status for f in flows)),
        skipped_files=tuple(SkippedFileRow(file=f, reason=r) for f, r in skipped),
        canary_run=_canary_run(prove),
        methodology=AuditMethodology(
            detector_versions=_detector_versions(),
            registry_version=1,
            sinks_known=len(sinks),
            sink_ids=tuple(sorted(s.id for s in sinks)),
            limits_note=_LIMITS_NOTE,
            not_detected_note=_NOT_DETECTED_NOTE,
            config_fingerprint=_config_fingerprint(root, sinks, excludes),
        ),
    )


def run_audit(
    root: Path,
    *,
    sinks: tuple[SinkDef, ...] | None = None,
    exclude: frozenset[str] = DEFAULT_EXCLUDES,
    now: datetime | None = None,
    prove: ProveResult | None = None,
) -> AuditSummary:
    """Discover and classify every egress flow under `root`.

    `now` is injectable so a test can assert two runs are byte-identical.
    `prove` is the result of a canary run, when one was asked for; without
    it every flow reports `not_run` and nothing is called confirmed.
    """
    registry = sinks if sinks is not None else default_registry()
    flows, skipped, examined = discover(root, registry, exclude=exclude)
    return build_summary(
        root=root,
        flows=flows,
        skipped=tuple((s.file, s.reason) for s in skipped),
        files_examined=examined,
        sinks=registry,
        excludes=exclude,
        generated_at=now if now is not None else datetime.now(timezone.utc),
        prove=prove,
    )
