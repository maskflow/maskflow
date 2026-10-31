"""`--prove`: run the project, watch for canaries, attribute escapes to flows.

This is what makes the report's promise literal. Discovery says a path
*looks* unmasked; this runs the application with synthetic identities in its
data, intercepts every provider-bound request before it leaves the process,
and reports which canary reached which host from which line -- with the
Python stack captured at send time.

The sequence, and why it is in this order:

1. **Refuse production.** Before anything is written, see `seeding.safety`.
2. **Generate and self-check canaries.** A canary MaskFlow would not detect
   proves nothing, so the manifest is verified against the pack's own
   validators first and the run aborts if any value fails.
3. **Seed.** Each adapter records a backup of whatever it rewrites.
4. **Run the project's command in a subprocess** with the interception hook
   installed via `sitecustomize`, so the patches are in place before the
   application imports its HTTP client.
5. **Restore the tree**, in a `finally`, so an interrupted audit still
   leaves the repository as it found it.
6. **Attribute** each escape to a discovered flow by matching the captured
   stack against the flow inventory.

Step 6 is the one worth explaining. A capture's stack is mostly SDK
internals; the useful frame is the deepest one inside the audited tree. We
match that frame to a flow on (file, line) first, and fall back to
(file, enclosing function) -- because the line a request is *sent* from is
the SDK's call site inside the user's function, which is usually but not
always the exact line discovery recorded. An escape that matches no flow is
not discarded: it is reported as unattributed, which means discovery missed
a sink and the registry needs an entry. That is the most valuable bug
report this tool can produce about itself.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .canary.manifest import CanaryManifest, build_manifest
from .discovery.flows import Flow
from .intercept.hook import CANARY_PREFIX, DUMP_PATH_VAR
from .intercept.sitecustomize_template import SITECUSTOMIZE
from .seeding.adapters import ADAPTERS
from .seeding.base import Seeder, SeedResult
from .seeding.safety import assert_not_production

#: What to run when the project does not say. A test suite is the one
#: command almost every project has that exercises its own code paths.
DEFAULT_COMMAND: tuple[str, ...] = ("python", "-m", "pytest", "-q")

#: How long the project's command may run before the audit gives up. A
#: suite that hangs must not hang the audit forever.
DEFAULT_TIMEOUT = 900


@dataclass(frozen=True)
class AttributedEscape:
    """One canary escape, tied to the line that sent it."""

    entity_type: str
    form: str
    identity: int
    host: str
    method: str
    path: str
    library: str
    #: The audited tree's own frames, innermost last: the leak's call path.
    app_stack: tuple[str, ...]
    flow_id: str = ""  # empty when discovery never found this sink


@dataclass(frozen=True)
class ProveResult:
    """Everything the canary run established."""

    manifest: CanaryManifest
    command: tuple[str, ...]
    exit_code: int
    ran: bool
    escapes: tuple[AttributedEscape, ...]
    #: Flow ids a captured request was attributed to, escape or not. A flow
    #: in here was genuinely exercised by the run; a flow absent from it was
    #: never reached, which is NOT the same as proven safe -- the report
    #: distinguishes `contained` from `not_exercised` on exactly this.
    exercised_flow_ids: frozenset[str]
    captures_seen: int
    seed_results: tuple[SeedResult, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    @property
    def escaped_flow_ids(self) -> frozenset[str]:
        return frozenset(e.flow_id for e in self.escapes if e.flow_id)

    @property
    def unattributed(self) -> tuple[AttributedEscape, ...]:
        return tuple(e for e in self.escapes if not e.flow_id)

    def escapes_for(self, flow_id: str) -> tuple[AttributedEscape, ...]:
        return tuple(e for e in self.escapes if e.flow_id == flow_id)


def _flow_index(
    flows: tuple[Flow, ...],
) -> tuple[dict[tuple[str, int], str], dict[tuple[str, str], str]]:
    """Lookups from (file, line) and (file, function) to flow id."""
    by_line: dict[tuple[str, int], str] = {}
    by_function: dict[tuple[str, str], str] = {}
    for flow in flows:
        by_line[(flow.file, flow.line)] = flow.flow_id
        # A function with several sinks maps to the first by file order;
        # the line match above is what disambiguates the common case.
        by_function.setdefault((flow.file, flow.function.split(".")[-1]), flow.flow_id)
    return by_line, by_function


def _attribute(
    record: dict[str, Any], root: Path, flows: tuple[Flow, ...]
) -> tuple[str, list[AttributedEscape]]:
    by_line, by_function = _flow_index(flows)
    resolved_root = str(root.resolve())

    raw_stack = record.get("stack") or []
    app_frames: list[dict[str, Any]] = []
    for frame in raw_stack:
        if not isinstance(frame, dict):
            continue
        try:
            path = str(Path(str(frame.get("file", ""))).resolve())
        except (OSError, ValueError):
            continue
        if path.startswith(resolved_root):
            relative = Path(path).relative_to(resolved_root).as_posix()
            app_frames.append({**frame, "relative": relative})

    flow_id = ""
    for frame in reversed(app_frames):  # innermost first
        relative = str(frame["relative"])
        line = int(frame.get("line") or 0)
        function = str(frame.get("function") or "")
        if (relative, line) in by_line:
            flow_id = by_line[(relative, line)]
            break
        if (relative, function) in by_function:
            flow_id = by_function[(relative, function)]
            break

    app_stack = tuple(
        f"{frame['relative']}:{frame.get('line')} in {frame.get('function')}"
        for frame in app_frames
    )

    out: list[AttributedEscape] = []
    for escape in record.get("escapes") or []:
        if not isinstance(escape, dict):
            continue
        out.append(
            AttributedEscape(
                entity_type=str(escape.get("entity_type", "")),
                form=str(escape.get("form", "")),
                identity=int(escape.get("identity") or 0),
                host=str(record.get("host", "")),
                method=str(record.get("method", "")),
                path=str(record.get("path", "")),
                library=str(record.get("library", "")),
                app_stack=app_stack,
                flow_id=flow_id,
            )
        )
    return flow_id, out


def _child_env(dump_path: Path, hook_dir: Path, manifest: CanaryManifest) -> dict[str, str]:
    env = dict(os.environ)
    env[DUMP_PATH_VAR] = str(dump_path)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{hook_dir}{os.pathsep}{existing}" if existing else str(hook_dir)
    for entity_type, value in manifest.for_identity(0).items():
        env[f"{CANARY_PREFIX}{entity_type}"] = value
    env["MASKFLOW_AUDIT_SEED"] = str(manifest.seed)
    # The child must not be told to skip its own slow paths by a stale flag.
    env.pop("PYTEST_ADDOPTS", None)
    return env


def run_canary_proof(
    root: Path,
    flows: tuple[Flow, ...],
    *,
    command: tuple[str, ...] | None = None,
    seed: int | None = None,
    identities: int = 1,
    allow_env: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> ProveResult:
    """Seed canaries, run the project, and attribute every escape."""
    warnings = tuple(assert_not_production(root, allow_env=allow_env))
    manifest = build_manifest(seed=seed, identities=identities)
    resolved_command = command or DEFAULT_COMMAND

    seeders: list[Seeder] = [adapter() for adapter in ADAPTERS]
    applied: list[tuple[Seeder, SeedResult]] = []
    escapes: list[AttributedEscape] = []
    exercised: set[str] = set()
    captures_seen = 0
    exit_code = -1
    ran = False
    note = ""

    try:
        for seeder in seeders:
            if not seeder.detect(root):
                continue
            result = seeder.seed(root, manifest)
            applied.append((seeder, result))

        with tempfile.TemporaryDirectory(prefix="maskflow-audit-") as workspace:
            hook_dir = Path(workspace)
            (hook_dir / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
            dump_path = hook_dir / "captures.json"

            argv = list(resolved_command)
            if argv and argv[0] == "python":
                argv[0] = sys.executable

            try:
                completed = subprocess.run(
                    argv,
                    cwd=root,
                    env=_child_env(dump_path, hook_dir, manifest),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                exit_code = completed.returncode
                ran = True
                if exit_code != 0:
                    # Deliberately NOT capturing the child's output into the
                    # result. During a seeded run its stdout/stderr contains
                    # canaries, and in a real project it contains whatever
                    # that application logs -- putting it in a report a DPO
                    # retains, or in a CI log, would be the leak this tool
                    # exists to prevent. The exit code is reported; the
                    # output stays in the user's own terminal when they
                    # re-run the command themselves.
                    note = (
                        f"the project's command exited {exit_code}; canary results below "
                        "are from whatever it managed to run. Re-run it yourself to see "
                        "why -- its output is deliberately not captured here, because "
                        "during a seeded run it contains canary values."
                    )
            except subprocess.TimeoutExpired:
                note = f"the project's command exceeded {timeout}s and was stopped"
            except (OSError, ValueError) as exc:
                note = f"could not run {argv[0]!r} ({exc.__class__.__name__})"

            if dump_path.is_file():
                try:
                    payload = json.loads(dump_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = {}
                records = payload.get("captures") or []
                captures_seen = len(records)
                for record in records:
                    if isinstance(record, dict):
                        flow_id, found = _attribute(record, root, flows)
                        if flow_id:
                            exercised.add(flow_id)
                        escapes.extend(found)
            elif ran and not note:
                note = (
                    "the run produced no capture file -- the command may not have "
                    "exercised any LLM path, or it spawned an interpreter that did "
                    "not inherit PYTHONPATH"
                )
    finally:
        # Restore in reverse order, and never let a restore failure mask the
        # result: a tree left dirty is bad, a crash that hides a finding is
        # worse.
        for seeder, result in reversed(applied):
            try:
                seeder.restore(root, result)
            except Exception:  # noqa: BLE001
                pass

    return ProveResult(
        manifest=manifest,
        command=tuple(resolved_command),
        exit_code=exit_code,
        ran=ran,
        escapes=tuple(escapes),
        exercised_flow_ids=frozenset(exercised),
        captures_seen=captures_seen,
        seed_results=tuple(result for _, result in applied),
        warnings=warnings,
        note=note,
    )


def parse_command(raw: str | None) -> tuple[str, ...] | None:
    """`--flows "pytest -q tests/"` -> argv. None when not given."""
    if not raw:
        return None
    return tuple(shlex.split(raw))
