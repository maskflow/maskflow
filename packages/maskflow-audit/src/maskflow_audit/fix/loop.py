"""The orchestrator: one worker per leaking flow, gated on acceptance.

Model-agnostic by taking a **callable**, not a client: `ModelFn` is
`(system, user) -> str`. That is the same choice the SDK made for
`mask_and_call`, for the same reason -- MaskFlow depends on no provider's
package, and the user supplies their own key inside their own closure.

The worker's tool set is deliberately narrow: read a file, propose a
unified diff, and nothing else. It cannot run commands, cannot install
packages, and cannot reach the network. Everything that decides whether a
change is kept lives in `gates.py` and is evaluated by this module, so the
model has no path to influencing its own verdict.

Order of work is confirmed leaks first, then high-confidence predictions,
because a proven leak is worth a retry budget and a guess is not.

The model only ever sees source code and canary *metadata* -- entity types
and counts. It is never shown a canary value, a column value, or the
captured payload.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..report.summary import AuditSummary, FlowRow
from .gates import GateOutcome, GateReport, run_gates

#: (system prompt, user prompt) -> the model's reply. Supplied by the
#: caller, closing over their own client and key.
ModelFn = Callable[[str, str], str]

DEFAULT_MAX_ATTEMPTS = 3

_SYSTEM = """\
You are fixing an unmasked LLM egress path in a Python codebase, using the \
MaskFlow library. Reply with a unified diff and nothing else: no prose, no \
fences, no commentary.

Rules you must not break:
- Add no dependency other than MaskFlow's own packages.
- Never modify a test file, a conftest, or anything under tests/.
- Introduce no new URL, base_url, credential, secret, or subprocess call.
- Preserve the round trip: if you mask a prompt, unmask the response with \
the same mapping wherever the application expects real values.
- Match the surrounding code's style, imports, and typing conventions.

Pick the cheapest fix that fits: routing the client through the MaskFlow \
gateway's base_url, installing the matching framework integration, or \
wrapping the call site with mask()/unmask().
"""


@dataclass(frozen=True)
class FixAttempt:
    """One model proposal and what the gates made of it."""

    attempt: int
    diff: str = field(repr=False)
    applied: bool
    gates: GateReport | None
    error: str = ""


@dataclass(frozen=True)
class FixResult:
    """The outcome for one flow."""

    flow_id: str
    file: str
    line: int
    fixed: bool
    attempts: tuple[FixAttempt, ...]
    reason: str = ""

    @property
    def accepted_diff(self) -> str:
        for attempt in self.attempts:
            if attempt.applied and attempt.gates is not None and attempt.gates.accepted:
                return attempt.diff
        return ""


@dataclass(frozen=True)
class FixReport:
    """Everything the loop did."""

    results: tuple[FixResult, ...]
    model_available: bool
    note: str = ""

    @property
    def fixed(self) -> tuple[FixResult, ...]:
        return tuple(r for r in self.results if r.fixed)

    @property
    def unfixed(self) -> tuple[FixResult, ...]:
        return tuple(r for r in self.results if not r.fixed)

    def pr_body(self) -> str:
        """Before/after evidence for a pull request.

        Deliberately concrete: a reviewer should see what was proven, not
        that a tool was run.
        """
        if not self.fixed:
            return "No fix passed every gate; nothing to propose."
        lines = ["## MaskFlow audit — masked LLM egress paths", ""]
        for result in self.fixed:
            gates = result.attempts[-1].gates
            lines.append(f"- **{result.file}:{result.line}** (`{result.flow_id}`)")
            if gates is not None:
                lines.append(f"  - gates: {gates.summary()}")
        if self.unfixed:
            lines += ["", "### Could not fix automatically", ""]
            for result in self.unfixed:
                lines.append(f"- **{result.file}:{result.line}** — {result.reason}")
        return "\n".join(lines)


def _flow_prompt(flow: FlowRow, source: str) -> str:
    sources = (
        ", ".join(f"{s.kind}:{s.detail}" if s.detail else s.kind for s in flow.sources)
        or "not traced"
    )
    if flow.canary_escapes:
        entities = sorted({e.entity_type for e in flow.canary_escapes})
        evidence = (
            f"PROVEN: a synthetic {', '.join(entities)} canary was observed reaching "
            f"{flow.canary_escapes[0].host} from this line."
        )
    else:
        evidence = f"PREDICTED (confidence: {flow.confidence}); no canary run has confirmed it."

    return (
        f"File: {flow.file}\n"
        f"Line: {flow.line}\n"
        f"Enclosing function: {flow.function or '<module>'}\n"
        f"Sink: {flow.sink_id} -> {flow.provider}\n"
        f"Masking status: {flow.masking_status} ({flow.masking_reason})\n"
        f"Payload argument(s): {', '.join(flow.payload_args) or 'unknown'}\n"
        f"Data reaching it: {sources}\n"
        f"{evidence}\n\n"
        f"--- {flow.file}\n{source}\n"
    )


def _apply_diff(root: Path, diff: str) -> tuple[bool, str]:
    """Apply a unified diff with `git apply`. Returns (applied, error)."""
    if not diff.strip():
        return False, "the model returned an empty diff"
    try:
        completed = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=root,
            input=diff,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"could not run git apply ({exc.__class__.__name__})"
    if completed.returncode != 0:
        return False, "git apply rejected the diff (it did not match the file)"
    return True, ""


def _revert(root: Path, diff: str) -> None:
    """Undo an applied diff, so a rejected attempt leaves no trace."""
    try:
        subprocess.run(
            ["git", "apply", "--reverse", "--whitespace=nowarn", "-"],
            cwd=root,
            input=diff,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _order(summary: AuditSummary) -> list[FlowRow]:
    leaks = [f for f in summary.flows if f.canary_status == "escaped"]
    predicted = [
        f
        for f in summary.flows
        if f.canary_status != "escaped"
        and f.masking_status in {"unmasked", "unknown"}
        and f.confidence in {"high", "medium"}
    ]
    return leaks + predicted


def run_fix_loop(
    root: Path,
    summary: AuditSummary,
    model: ModelFn | None,
    *,
    test_command: tuple[str, ...] = ("python", "-m", "pytest", "-q"),
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    recheck: Callable[[str], bool | None] | None = None,
    round_trip_check: Callable[[str], bool | None] | None = None,
) -> FixReport:
    """Work through the leaking flows, accepting only gated fixes.

    `recheck(flow_id)` re-runs the canary harness scoped to one flow and
    returns whether a canary still escaped; `round_trip_check(flow_id)`
    verifies the application still shows real values. Both return None
    when they cannot tell, which the gates treat as SKIPPED -- and SKIPPED
    blocks acceptance, so an unverifiable fix is never kept.
    """
    if model is None:
        return FixReport(
            results=(),
            model_available=False,
            note=(
                "no model was configured, so no fix was attempted. Use --handoff to "
                "write a task file for your own coding agent instead -- it needs no key."
            ),
        )

    results: list[FixResult] = []
    for flow in _order(summary):
        path = root / flow.file
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            results.append(
                FixResult(
                    flow_id=flow.flow_id,
                    file=flow.file,
                    line=flow.line,
                    fixed=False,
                    attempts=(),
                    reason=f"could not read the file ({exc.__class__.__name__})",
                )
            )
            continue

        attempts: list[FixAttempt] = []
        fixed = False
        reason = ""

        for attempt_number in range(1, max_attempts + 1):
            prompt = _flow_prompt(flow, source)
            if attempts:
                last = attempts[-1]
                detail = last.error or (
                    "; ".join(last.gates.reasons) if last.gates is not None else ""
                )
                prompt += (
                    f"\nYour previous attempt was rejected: {detail}\n"
                    "Produce a different diff that does not repeat that mistake.\n"
                )
            try:
                diff = model(_SYSTEM, prompt)
            except Exception as exc:  # noqa: BLE001 -- any model failure is one attempt
                attempts.append(
                    FixAttempt(
                        attempt=attempt_number,
                        diff="",
                        applied=False,
                        gates=None,
                        error=f"the model call failed ({exc.__class__.__name__})",
                    )
                )
                continue

            applied, error = _apply_diff(root, diff)
            if not applied:
                attempts.append(
                    FixAttempt(
                        attempt=attempt_number, diff=diff, applied=False, gates=None, error=error
                    )
                )
                continue

            gates = run_gates(
                root,
                diff,
                test_command=test_command,
                canaries_escaped=recheck(flow.flow_id) if recheck else None,
                round_trip_ok=round_trip_check(flow.flow_id) if round_trip_check else None,
            )
            attempts.append(
                FixAttempt(attempt=attempt_number, diff=diff, applied=True, gates=gates)
            )

            if gates.accepted:
                fixed = True
                break

            # Rejected: put the tree back before the next attempt, so
            # attempts never stack on each other.
            _revert(root, diff)

        if not fixed:
            final: FixAttempt | None = attempts[-1] if attempts else None
            if final is None:
                reason = "no attempt was made"
            elif final.error:
                reason = final.error
            elif final.gates is not None:
                blocking = [
                    name
                    for name, outcome in (
                        ("tests", final.gates.tests),
                        ("canaries", final.gates.canaries),
                        ("round_trip", final.gates.round_trip),
                        ("no_new_surface", final.gates.no_new_surface),
                    )
                    if outcome is not GateOutcome.PASSED
                ]
                reason = (
                    f"could not fix automatically after {len(attempts)} attempt(s); "
                    f"gate(s) {', '.join(blocking)} did not pass"
                    + (f" ({'; '.join(final.gates.reasons[:2])})" if final.gates.reasons else "")
                )
            else:
                reason = f"could not fix automatically after {len(attempts)} attempt(s)"

        results.append(
            FixResult(
                flow_id=flow.flow_id,
                file=flow.file,
                line=flow.line,
                fixed=fixed,
                attempts=tuple(attempts),
                reason=reason,
            )
        )

    return FixReport(results=tuple(results), model_available=True)
