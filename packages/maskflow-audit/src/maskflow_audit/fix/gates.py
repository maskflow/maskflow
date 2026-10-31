"""The hard gates. A fix is accepted only if all of them hold.

This module is the reason the fix loop is safe to point at a repository.
A model that is allowed to edit code until the tests pass will, eventually,
edit the tests -- so the gates are checked by this module, not by the
model, and the model never sees a way to influence them.

All four must hold:

  1. the project's own tests pass;
  2. zero canaries escape on the flow being fixed;
  3. the round trip still works -- unmasked output contains the real values
     where the application expects them;
  4. no new network destination, permission, or secret appears in the diff.

Gate 4 exists because the cheapest way to make a leak "stop" is to send the
data somewhere else, and the cheapest way to make a test pass is to add a
credential. Both are caught by reading the diff, not by running it.

**Never weaken a test to pass a gate.** A diff that edits a test file at
all is rejected outright before anything is run, because the whole premise
of gate 1 is that the suite is the unmodified arbiter.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class GateOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"  # could not be evaluated; never counts as a pass


@dataclass(frozen=True)
class GateReport:
    """Per-gate results for one candidate fix."""

    tests: GateOutcome
    canaries: GateOutcome
    round_trip: GateOutcome
    no_new_surface: GateOutcome
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def accepted(self) -> bool:
        """Every gate must be PASSED. A SKIPPED gate blocks acceptance.

        Deliberately strict: "we could not check the round trip" is not a
        reason to ship a change to somebody's masking layer.
        """
        return all(
            outcome is GateOutcome.PASSED
            for outcome in (self.tests, self.canaries, self.round_trip, self.no_new_surface)
        )

    def summary(self) -> str:
        return (
            f"tests={self.tests.value} canaries={self.canaries.value} "
            f"round_trip={self.round_trip.value} no_new_surface={self.no_new_surface.value}"
        )


#: Paths a fix may never touch. Editing the suite is how a model makes a
#: failing gate green without fixing anything.
_TEST_PATH = re.compile(r"(^|/)(tests?|spec|conftest\.py)(/|$)|(^|/)test_[^/]*\.py$")

#: Diff lines that introduce a new outbound destination.
_NEW_DESTINATION = re.compile(
    r"""^\+.*(
        https?://
      | \bbase_url\s*=
      | \bendpoint\s*=
      | \bwebhook
      | \bsmtp
      | socket\.(connect|create_connection)
    )""",
    re.IGNORECASE | re.VERBOSE,
)

#: Diff lines that introduce a credential or widen permissions.
_NEW_SECRET = re.compile(
    r"""^\+.*(
        \b(api_key|apikey|secret|token|password|passwd|credential)\b\s*[:=]
      | \bos\.environ\[
      | \bchmod\b
      | \bsudo\b
      | \beval\(
      | \bexec\(
      | \bsubprocess\b
      | \b__import__\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)

#: MaskFlow's own imports are the expected content of a fix, so a line
#: adding one is exempt from the destination check -- `from maskflow import
#: mask` is the fix, not a new egress path.
_ALLOWED = re.compile(r"^\+.*\b(maskflow|maskflow_\w+)\b")


def _changed_paths(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            paths.append(line[4:].strip().removeprefix("b/"))
    return paths


def check_diff_surface(diff: str) -> tuple[GateOutcome, list[str]]:
    """Gates 4 and the test-file prohibition, read straight off the diff."""
    reasons: list[str] = []

    for path in _changed_paths(diff):
        if _TEST_PATH.search(path):
            reasons.append(
                f"the diff modifies {path}, which is a test file -- a fix may never "
                "weaken the suite that validates it"
            )

    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if _ALLOWED.search(line):
            continue
        if _NEW_DESTINATION.search(line):
            reasons.append(f"the diff adds a new network destination: {line.strip()[:120]}")
        if _NEW_SECRET.search(line):
            reasons.append(
                f"the diff adds a credential or widens permissions: {line.strip()[:120]}"
            )

    return (GateOutcome.FAILED if reasons else GateOutcome.PASSED), reasons


def run_project_tests(
    root: Path, command: tuple[str, ...], *, timeout: int = 900
) -> tuple[GateOutcome, str]:
    """Gate 1. Returns (outcome, reason) -- never the suite's output.

    The output is withheld on purpose: during a fix run the tests execute
    against seeded data, so their stdout can contain canary values, and a
    gate report is a thing people paste into PRs.
    """
    argv = list(command)
    if argv and argv[0] == "python":
        argv[0] = sys.executable
    try:
        completed = subprocess.run(
            argv, cwd=root, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return GateOutcome.SKIPPED, f"the test command exceeded {timeout}s"
    except (OSError, ValueError) as exc:
        return GateOutcome.SKIPPED, f"could not run {argv[0]!r} ({exc.__class__.__name__})"
    if completed.returncode == 0:
        return GateOutcome.PASSED, ""
    return (
        GateOutcome.FAILED,
        f"the project's tests exited {completed.returncode} (output withheld: during a "
        "seeded run it can contain canary values)",
    )


def run_gates(
    root: Path,
    diff: str,
    *,
    test_command: tuple[str, ...],
    canaries_escaped: bool | None,
    round_trip_ok: bool | None,
    timeout: int = 900,
) -> GateReport:
    """Evaluate every gate for one candidate fix.

    `canaries_escaped` and `round_trip_ok` are None when the caller could
    not determine them, which maps to SKIPPED -- and SKIPPED blocks
    acceptance.
    """
    reasons: list[str] = []

    surface, surface_reasons = check_diff_surface(diff)
    reasons += surface_reasons

    if surface is GateOutcome.FAILED:
        # A diff that touches tests or adds a destination is rejected
        # without running anything: executing it is both pointless and the
        # riskier order of operations.
        return GateReport(
            tests=GateOutcome.SKIPPED,
            canaries=GateOutcome.SKIPPED,
            round_trip=GateOutcome.SKIPPED,
            no_new_surface=surface,
            reasons=tuple(reasons),
        )

    tests, test_reason = run_project_tests(root, test_command, timeout=timeout)
    if test_reason:
        reasons.append(test_reason)

    if canaries_escaped is None:
        canaries = GateOutcome.SKIPPED
        reasons.append("the canary harness did not run for this flow, so no leak was disproven")
    elif canaries_escaped:
        canaries = GateOutcome.FAILED
        reasons.append("a canary still escaped on this flow after the fix")
    else:
        canaries = GateOutcome.PASSED

    if round_trip_ok is None:
        round_trip = GateOutcome.SKIPPED
        reasons.append("the round trip could not be verified for this flow")
    elif round_trip_ok:
        round_trip = GateOutcome.PASSED
    else:
        round_trip = GateOutcome.FAILED
        reasons.append(
            "the round trip broke -- unmasked output no longer carries the real values "
            "where the application expects them"
        )

    return GateReport(
        tests=tests,
        canaries=canaries,
        round_trip=round_trip,
        no_new_surface=surface,
        reasons=tuple(reasons),
    )
