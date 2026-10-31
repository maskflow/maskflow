"""Rich rendering for `maskflow audit`. Kept separate from
commands/audit_cmd.py so the command body stays thin, same split as
doctor.py/doctor_render.py and bench_render.py.

Only type-checked against maskflow-audit (TYPE_CHECKING guard below,
`from __future__ import annotations` keeps every annotation an unevaluated
string at runtime) -- this module never constructs an AuditSummary itself,
only duck-types over one handed in by audit_cmd.py, so it never needs the
optional [audit] extra installed just to be imported.

Nothing here reads a value: an AuditSummary carries identifiers and counts
only (see maskflow_audit.report.summary's docstring), so this renderer
cannot print PII even by accident."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from maskflow_audit.baseline.diff import CiVerdict
    from maskflow_audit.fix.loop import FixReport
    from maskflow_audit.report.summary import AuditSummary

# Same rationale as doctor_render.py's: a fixed width so output doesn't
# wrap unpredictably under a non-tty (CI logs, CliRunner in tests).
CONSOLE_WIDTH = 100

#: Longest source list shown per flow before it is summarised. The full
#: list is always in audit.json; the table is a triage view, and a cell
#: that folds character-by-character (which is what happens when five
#: column names meet a long fixture path at a fixed console width) is
#: worse than no cell at all.
MAX_SOURCES_SHOWN = 2


#: How a status reads in the terminal, and the colour it reads in.
_STATUS_STYLE: dict[str, tuple[str, str]] = {
    "unmasked": ("UNMASKED", "bold red"),
    "unknown": ("unknown", "yellow"),
    "masked_via_mask_call": ("masked: mask()", "green"),
    "masked_via_gateway_base_url": ("masked: gateway", "green"),
    "masked_via_integration": ("masked: integration", "green"),
}

#: A proven leak overrides the static status entirely -- it is the one
#: line in the output that is evidence rather than inference.
_LEAK_STYLE = ("LEAK PROVEN", "bold white on red")

#: What a flow's canary verdict adds to its detail line. `not_exercised`
#: is spelled out because it is the one a reader is most likely to
#: misread as safe.
_CANARY_NOTE: dict[str, str] = {
    "escaped": "canary escaped",
    "contained": "canary contained",
    "not_exercised": "not exercised by the run",
    "not_run": "",
}


def _sources(flow: object) -> str:
    """A compact source summary: at most MAX_SOURCES_SHOWN, then a count."""
    sources = flow.sources  # type: ignore[attr-defined]
    shown = [f"{s.kind}:{s.detail}" if s.detail else s.kind for s in sources]
    if not shown:
        return ""
    if len(shown) <= MAX_SOURCES_SHOWN:
        return ", ".join(shown)
    return ", ".join(shown[:MAX_SOURCES_SHOWN]) + f" (+{len(shown) - MAX_SOURCES_SHOWN})"


def make_console(*, stderr: bool = True) -> Console:
    """Human output goes to stderr so `--out -` stays pipeable."""
    return Console(width=CONSOLE_WIDTH, stderr=stderr, highlight=False, soft_wrap=False)


def render_summary(console: Console, summary: AuditSummary) -> None:
    """The headline, the flow table, and the honest caveat."""
    coverage = summary.coverage
    console.print()
    console.print(f"[bold]{summary.headline}[/bold]")

    if coverage.total_flows == 0:
        console.print(
            "[yellow]No LLM egress paths found.[/yellow] That means none of the sinks in "
            "the registry appear in this tree -- not that none exist. See the limits note "
            "in the report."
        )
        return

    parts = []
    if coverage.confirmed_leaks:
        # Listed first and loudest: it is the only number here that is
        # evidence rather than inference.
        parts.append(f"[bold white on red] {coverage.confirmed_leaks} PROVEN LEAK(S) [/]")
    if coverage.unmasked:
        parts.append(f"[bold red]{coverage.unmasked} unmasked[/bold red]")
    if coverage.unknown:
        parts.append(f"[yellow]{coverage.unknown} unknown[/yellow]")
    if coverage.masked:
        parts.append(f"[green]{coverage.masked} masked[/green]")
    console.print(" · ".join(parts))
    console.print()

    # Deliberately not a rich Table. At a fixed console width a table
    # redistributes space between columns, so one long repo-relative path
    # starves its neighbours until a cell folds one character per line --
    # which is what a real audit of a real tree produces. A two-line block
    # per flow stays readable at any width and never truncates a path.
    for flow in summary.flows:
        if flow.canary_status == "escaped":
            label, style = _LEAK_STYLE
        else:
            label, style = _STATUS_STYLE.get(flow.masking_status, (flow.masking_status, ""))
        badge = f"[{style}]{label:<20}[/{style}]" if style else f"{label:<20}"
        console.print(
            f"{badge} {flow.file}:{flow.line}  [dim]{flow.sink_id} · {flow.flow_id}[/dim]"
        )
        sources = _sources(flow)
        detail = f"from {sources}" if sources else "source not traced"
        note = _CANARY_NOTE.get(flow.canary_status, "")
        suffix = f" · {note}" if note else ""
        console.print(f"{'':<20} [dim]{detail} · conf: {flow.confidence}{suffix}[/dim]")
        for escape in flow.canary_escapes[:1]:
            entities = ", ".join(sorted({e.entity_type for e in flow.canary_escapes}))
            console.print(
                f"{'':<20} [red]canary {entities} reached {escape.host}{escape.path}"
                f" ({escape.form})[/red]"
            )
            for frame in escape.app_stack[-3:]:
                console.print(f"{'':<22} [dim]{frame}[/dim]")

    run = summary.canary_run
    if not summary.scope.canaries_run:
        console.print(
            "[dim]Canaries were not run, so every finding above is predicted, not "
            "proven. Re-run with --prove to confirm which paths actually leak.[/dim]"
        )
    elif run is not None:
        console.print(
            f"[dim]Canary run: seed {run.seed} · {run.requests_intercepted} request(s) "
            f"intercepted (none sent) · {run.escapes_observed} escape(s) observed.[/dim]"
        )
        if run.unattributed_escapes:
            # Discovery missed a sink. This is the most useful bug report
            # the tool can produce about itself, so it is asked for.
            console.print(
                f"[yellow]{run.unattributed_escapes} escape(s) matched no discovered "
                "flow -- a canary got out through a path static analysis did not find. "
                "Please report it.[/yellow]"
            )
        if run.note:
            console.print(f"[yellow]{run.note}[/yellow]")
        for warning in run.warnings:
            console.print(f"[yellow]--allow-env override: {warning}[/yellow]")
    if summary.skipped_files:
        console.print(
            f"[dim]{len(summary.skipped_files)} file(s) skipped (unparseable or "
            f"unreadable); see skipped_files in the report.[/dim]"
        )


def render_ci(console: Console, verdict: CiVerdict, summary: AuditSummary) -> None:
    """The `--ci` gate's output: short, and PR-friendly.

    GitHub Actions workflow commands (`::error::`, `::notice::`) so a
    failure annotates the run rather than hiding in a log, matching the
    scan action's behaviour.
    """
    if verdict.skipped:
        console.print(f"[yellow]{verdict.summary_line()}[/yellow]")
        console.print(f"::notice::{verdict.summary_line()}")
        return

    if verdict.ok:
        console.print(f"[green]{verdict.summary_line()}[/green]")
        console.print(f"::notice::{summary.headline}")
        return

    console.print(f"[bold red]{verdict.summary_line()}[/bold red]\n")
    for problem in verdict.problems:
        console.print(f"  [red]•[/red] {problem}")
    console.print(f"\n::error::{verdict.summary_line()}")
    console.print(
        "[dim]If these paths are intentional, re-run `maskflow audit --baseline` "
        "and commit the updated baseline.[/dim]"
    )


def render_fix(console: Console, report: FixReport) -> None:
    """What the fix loop did, or why it did nothing."""
    if not report.model_available:
        console.print(f"\n[yellow]{report.note}[/yellow]")
        return

    console.print()
    for result in report.fixed:
        gates = result.attempts[-1].gates
        console.print(f"[green]FIXED[/green] {result.file}:{result.line} ({result.flow_id})")
        if gates is not None:
            console.print(f"{'':<6}[dim]{gates.summary()}[/dim]")
    for result in report.unfixed:
        console.print(f"[yellow]NOT FIXED[/yellow] {result.file}:{result.line}")
        console.print(f"{'':<10}[dim]{result.reason}[/dim]")
    if report.fixed:
        console.print("\n[dim]Suggested PR body:[/dim]")
        console.print(report.pr_body())
