"""`maskflow audit <path>` -- find every place a codebase sends text to an
LLM, prove which of those paths leak, and fix them.

`maskflow scan` asks what PII already reached a provider, from logs. This
asks the forward question, from source: where can text leave, and is it
guarded? With `--prove` it stops guessing -- it seeds synthetic identities,
runs the project, intercepts every provider-bound request before it leaves
the process, and reports which canary reached which host from which line.

`maskflow-audit` is an **optional** dependency (`pip install
'maskflow-cli[audit]'`) -- imported lazily here, same policy as
`maskflow_cli.evidence` and `bench_cmd.py`, so a bare CLI install (and the
standalone PyInstaller binary) doesn't require it and every other command
runs without it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from ..audit_render import make_console, render_ci, render_fix, render_summary

_MISSING = (
    "`maskflow audit` needs the audit extra -- install it with: pip install 'maskflow-cli[audit]'"
)

_EVIDENCE_MISSING = (
    "--evidence needs the evidence extra too -- install it with: "
    "pip install 'maskflow-cli[audit,evidence]'"
)

# Ruff B008: ruff allows a bare typer.Argument()/Option() in a default, but
# not a nested call inside one (the Path(".") below), so the argument and
# the list/Path-defaulted options are module-level singletons -- same
# pattern as scan/cmd.py's and explain_cmd.py's.
_PATH_ARGUMENT = typer.Argument(Path("."), help="Directory or file to audit.")
_OUT_OPTION = typer.Option(
    None, "--out", "-o", help="Write the report here ('-' for stdout). Default: audit.<format>."
)
_FORMAT_OPTION = typer.Option("json", "--format", help="json | html.")
_EXCLUDE_OPTION = typer.Option(
    [], "--exclude", help="Directory name to skip, repeatable. Adds to the defaults."
)
_PROVE_OPTION = typer.Option(
    False,
    "--prove",
    help="Seed canaries, run the project, and confirm which paths actually leak.",
)
_FLOWS_OPTION = typer.Option(
    None,
    "--flows",
    help="Command --prove should run (default: python -m pytest -q).",
)
_SEED_OPTION = typer.Option(
    None, "--seed", help="Canary seed, for reproducing a run. Default: fresh each time."
)
_IDENTITIES_OPTION = typer.Option(
    1, "--identities", min=1, help="How many synthetic people to seed."
)
_ALLOW_ENV_OPTION = typer.Option(
    False,
    "--allow-env",
    help="Seed even though the environment looks like a real deployment.",
)
_BASELINE_OPTION = typer.Option(
    False, "--baseline", help="Write maskflow-audit.baseline.json and exit."
)
_CI_OPTION = typer.Option(
    False, "--ci", help="Fail the build on a new unmasked path or a new confirmed leak."
)
_BASELINE_FILE_OPTION = typer.Option(
    None, "--baseline-file", help="Baseline path (default: maskflow-audit.baseline.json)."
)
_FIX_OPTION = typer.Option(False, "--fix", help="Agentic fix loop. Needs your own model key.")
_HANDOFF_OPTION = typer.Option(
    False,
    "--handoff",
    help="Write maskflow-audit-tasks.md for your own coding agent. No key needed.",
)
_EVIDENCE_OPTION = typer.Option(
    False, "--evidence", help="Emit metadata-only evidence events for this run."
)
_QUIET_OPTION = typer.Option(False, "--quiet", help="Suppress the terminal summary.")

_FORMATS = ("json", "html")


def _die(message: str, code: int = 1) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


def audit(  # noqa: PLR0913 -- a CLI surface, each option is deliberate
    path: Path = _PATH_ARGUMENT,
    out: Path | None = _OUT_OPTION,
    fmt: str = _FORMAT_OPTION,
    exclude: list[str] = _EXCLUDE_OPTION,
    prove: bool = _PROVE_OPTION,
    flows: str | None = _FLOWS_OPTION,
    seed: int | None = _SEED_OPTION,
    identities: int = _IDENTITIES_OPTION,
    allow_env: bool = _ALLOW_ENV_OPTION,
    baseline: bool = _BASELINE_OPTION,
    ci: bool = _CI_OPTION,
    baseline_file: Path | None = _BASELINE_FILE_OPTION,
    fix: bool = _FIX_OPTION,
    handoff: bool = _HANDOFF_OPTION,
    evidence: bool = _EVIDENCE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Audits a source tree for unmasked LLM egress paths.

    Writes a machine-readable report (audit.json) and prints a summary.
    Your code is parsed, never executed; with --prove the project's own
    outbound requests are intercepted before they reach a provider, so
    nothing is ever transmitted. See docs/audit.md for the full reference."""
    try:
        from maskflow_audit.api import run_audit
        from maskflow_audit.baseline import BASELINE_FILENAME, BaselineError, diff_against
        from maskflow_audit.baseline import write_baseline as write_baseline_file
        from maskflow_audit.canary.manifest import SelfCheckFailure
        from maskflow_audit.discovery.walk import DEFAULT_EXCLUDES, discover
        from maskflow_audit.fix import run_fix_loop, write_handoff
        from maskflow_audit.fix.handoff import HANDOFF_FILENAME
        from maskflow_audit.prove import parse_command, run_canary_proof
        from maskflow_audit.report import render
        from maskflow_audit.seeding.safety import ProductionLooksLikely
        from maskflow_audit.sinks.loader import RegistryError, default_registry
    except ModuleNotFoundError as exc:
        typer.echo(_MISSING, err=True)
        raise typer.Exit(code=1) from exc

    if fmt not in _FORMATS:
        _die(f"--format must be one of {', '.join(_FORMATS)} (got {fmt!r})")
    if not path.exists():
        _die(f"{path}: no such file or directory", code=2)
    if fix and handoff:
        _die("--fix and --handoff are alternatives; pass one or the other")

    excludes = DEFAULT_EXCLUDES | frozenset(exclude)
    console = make_console()

    try:
        registry = default_registry()
    except RegistryError as exc:
        # A malformed shipped registry is a packaging bug, not user error.
        _die(str(exc), code=1)
        return

    proof = None
    if prove:
        discovered, _, _ = discover(path, registry, exclude=excludes)
        try:
            proof = run_canary_proof(
                path,
                discovered,
                command=parse_command(flows),
                seed=seed,
                identities=identities,
                allow_env=allow_env,
            )
        except ProductionLooksLikely as exc:
            _die(str(exc), code=2)
            return
        except SelfCheckFailure as exc:
            # A canary MaskFlow would not detect proves nothing, so this is
            # fatal rather than a warning.
            _die(str(exc), code=1)
            return

    summary = run_audit(path, sinks=registry, exclude=excludes, prove=proof)

    baseline_path = baseline_file or (Path.cwd() / BASELINE_FILENAME)

    if baseline:
        write_baseline_file(baseline_path, summary)
        if not quiet:
            console.print(
                f"wrote {baseline_path} -- commit it, then gate your builds with "
                "`maskflow audit --ci`"
            )
        return

    if ci:
        try:
            verdict = diff_against(summary, baseline_path)
        except BaselineError as exc:
            _die(str(exc), code=1)
            return
        render_ci(console, verdict, summary)
        raise typer.Exit(code=verdict.exit_code)

    rendered = render(summary, fmt)
    destination = out if out is not None else Path(f"audit.{fmt}")
    if str(destination) == "-":
        sys.stdout.write(rendered)
    else:
        destination.write_text(rendered, encoding="utf-8")

    if handoff:
        handoff_path = Path.cwd() / HANDOFF_FILENAME
        tasks = write_handoff(handoff_path, summary)
        if not quiet:
            console.print(f"wrote {handoff_path} ({tasks} task(s))")

    if fix:
        # No model is wired in by default: the audit never carries a
        # provider dependency or a key. `model=None` reports that plainly
        # and points at --handoff, which needs neither.
        report = run_fix_loop(path, summary, model=None)
        render_fix(console, report)

    if evidence:
        try:
            from maskflow_audit.evidence import EvidenceExtraMissing, emit_audit_evidence

            count = emit_audit_evidence(summary, enabled=True)
        except ModuleNotFoundError as exc:
            typer.echo(_EVIDENCE_MISSING, err=True)
            raise typer.Exit(code=1) from exc
        except EvidenceExtraMissing as exc:
            typer.echo(_EVIDENCE_MISSING, err=True)
            raise typer.Exit(code=1) from exc
        if not quiet:
            console.print(f"emitted {count} metadata-only evidence event(s)")

    if not quiet:
        render_summary(console, summary)
        if str(destination) != "-":
            console.print(f"\nwrote {destination}")
