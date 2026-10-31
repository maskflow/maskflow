"""`--baseline` writes it; `--ci` diffs against it and fails the build.

The gate's whole value is that it is believed, which makes its failure mode
asymmetric in a specific way. The bench F1 gates iterate the *baseline's*
keys, so a newly added entity type is never a retroactive failure. Here the
asymmetry **inverts**: a newly appeared unmasked flow is exactly the
regression we are looking for, while a flow that disappeared is someone
deleting code and is never a failure.

So `--ci` fails on:

  * a flow id that is unmasked or unknown and was not in the baseline;
  * a flow that was masked in the baseline and is not now (a regression on
    a path somebody had already fixed);
  * a newly confirmed leak.

And deliberately does **not** fail on: a flow that vanished, a flow whose
line moved (flow ids are not line-based), a new flow that is masked, or a
drop in the total count.

Two conventions borrowed from the bench gates: every problem is collected
and reported together rather than failing on the first, and a missing
baseline file is a *skip* with the command to create it, not an error --
a gate that fails closed before anyone has opted in just gets deleted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..report.summary import AuditSummary

#: Where `--baseline` writes by default. Committed to the repository.
BASELINE_FILENAME: Final = "maskflow-audit.baseline.json"

#: Bumped when the baseline's own shape changes incompatibly. Separate from
#: the report's schema version: a baseline is a much smaller contract and
#: should not be invalidated every time the report grows a field.
BASELINE_SCHEMA_VERSION: Final = "1"

_MASKED_PREFIX = "masked"


class BaselineError(Exception):
    """The baseline file is unreadable or from an incompatible version."""


@dataclass(frozen=True)
class Baseline:
    """The accepted state of a repository's egress surface.

    Deliberately minimal: flow id -> masking status, plus the set of flows
    with a confirmed leak. No line numbers (they move), no sources (they
    are advisory), no counts (they are derivable). A baseline that carried
    everything would conflict on every unrelated edit, and a gate that
    conflicts constantly is a gate that gets bypassed.
    """

    schema_version: str
    statuses: dict[str, str]
    confirmed_leaks: tuple[str, ...]
    #: Human-readable only -- never compared, so a refactor that moves a
    #: call does not produce a diff.
    locations: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "statuses": dict(sorted(self.statuses.items())),
            "confirmed_leaks": sorted(self.confirmed_leaks),
            "locations": dict(sorted(self.locations.items())),
        }


@dataclass(frozen=True)
class CiVerdict:
    """The result of a `--ci` run."""

    ok: bool
    skipped: bool
    problems: tuple[str, ...]
    new_flows: tuple[str, ...]
    regressed_flows: tuple[str, ...]
    new_leaks: tuple[str, ...]
    note: str = ""

    @property
    def exit_code(self) -> int:
        # A skip is a pass: the gate has not been opted into yet.
        return 0 if (self.ok or self.skipped) else 1

    def summary_line(self) -> str:
        if self.skipped:
            return f"maskflow audit --ci: skipped ({self.note})"
        if self.ok:
            return "maskflow audit --ci: no new unmasked LLM egress paths"
        parts = []
        if self.new_leaks:
            parts.append(f"{len(self.new_leaks)} newly confirmed leak(s)")
        if self.new_flows:
            parts.append(f"{len(self.new_flows)} new unmasked/unknown path(s)")
        if self.regressed_flows:
            parts.append(f"{len(self.regressed_flows)} path(s) regressed")
        return "maskflow audit --ci: " + ", ".join(parts)


def build_baseline(summary: AuditSummary) -> Baseline:
    return Baseline(
        schema_version=BASELINE_SCHEMA_VERSION,
        statuses={f.flow_id: f.masking_status for f in summary.flows},
        confirmed_leaks=tuple(f.flow_id for f in summary.flows if f.canary_status == "escaped"),
        locations={f.flow_id: f"{f.file}:{f.line}" for f in summary.flows},
    )


def write_baseline(path: Path, summary: AuditSummary) -> Baseline:
    """Write the baseline, sorted, with a trailing newline.

    Sorted keys and a trailing newline so the committed file produces clean
    git diffs -- the same convention the bench rebaseline targets use.
    """
    baseline = build_baseline(summary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline.to_dict(), indent=2, sort_keys=True) + "\n", "utf-8")
    return baseline


def load_baseline(path: Path) -> Baseline:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BaselineError(f"{path}: not found") from exc
    except json.JSONDecodeError as exc:
        raise BaselineError(f"{path}: not valid JSON ({exc.__class__.__name__})") from exc

    if not isinstance(raw, dict):
        raise BaselineError(f"{path}: top level must be an object")
    version = raw.get("schema_version")
    if version != BASELINE_SCHEMA_VERSION:
        raise BaselineError(
            f"{path}: baseline schema {version!r} is not supported (this build reads "
            f"{BASELINE_SCHEMA_VERSION!r}) -- regenerate it with `maskflow audit --baseline`"
        )
    statuses = raw.get("statuses")
    if not isinstance(statuses, dict):
        raise BaselineError(f"{path}: `statuses` must be an object")

    return Baseline(
        schema_version=BASELINE_SCHEMA_VERSION,
        statuses={str(k): str(v) for k, v in statuses.items()},
        confirmed_leaks=tuple(str(x) for x in raw.get("confirmed_leaks") or ()),
        locations={str(k): str(v) for k, v in (raw.get("locations") or {}).items()},
    )


def _describe(flow_id: str, summary: AuditSummary) -> str:
    for flow in summary.flows:
        if flow.flow_id == flow_id:
            return f"{flow.file}:{flow.line} ({flow.sink_id} -> {flow.provider})"
    return flow_id


def diff_against(summary: AuditSummary, path: Path) -> CiVerdict:
    """Compare this run to a committed baseline."""
    if not path.exists():
        return CiVerdict(
            ok=True,
            skipped=True,
            problems=(),
            new_flows=(),
            regressed_flows=(),
            new_leaks=(),
            note=(
                f"no baseline at {path} -- create one with "
                f"`maskflow audit --baseline` and commit it"
            ),
        )

    baseline = load_baseline(path)
    problems: list[str] = []
    new_flows: list[str] = []
    regressed: list[str] = []
    new_leaks: list[str] = []

    for flow in summary.flows:
        was = baseline.statuses.get(flow.flow_id)
        is_guarded = flow.masking_status.startswith(_MASKED_PREFIX)

        if was is None:
            if not is_guarded:
                new_flows.append(flow.flow_id)
                problems.append(
                    f"NEW unguarded egress path: {_describe(flow.flow_id, summary)} "
                    f"[{flow.masking_status}] {flow.flow_id}"
                )
        elif was.startswith(_MASKED_PREFIX) and not is_guarded:
            regressed.append(flow.flow_id)
            problems.append(
                f"REGRESSED: {_describe(flow.flow_id, summary)} was {was}, is now "
                f"{flow.masking_status} ({flow.flow_id})"
            )

        if flow.canary_status == "escaped" and flow.flow_id not in baseline.confirmed_leaks:
            new_leaks.append(flow.flow_id)
            entities = sorted({e.entity_type for e in flow.canary_escapes})
            problems.append(
                f"NEW CONFIRMED LEAK: canary {', '.join(entities)} reached a provider from "
                f"{_describe(flow.flow_id, summary)} ({flow.flow_id})"
            )

    return CiVerdict(
        ok=not problems,
        skipped=False,
        problems=tuple(problems),
        new_flows=tuple(new_flows),
        regressed_flows=tuple(regressed),
        new_leaks=tuple(new_leaks),
    )
