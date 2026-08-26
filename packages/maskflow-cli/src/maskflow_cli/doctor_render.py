"""Rich rendering for `maskflow doctor`. Kept separate from doctor.py's pure
data gathering so the checks themselves are testable without a console."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.table import Table

from .doctor import ComponentCheck, DoctorReport, EntityCheck

# A fixed width rather than terminal auto-detection: `maskflow doctor`'s
# longer detail strings (e.g. "MISSING (python -m spacy download ...)")
# would otherwise wrap unpredictably under a non-tty (CI logs, CliRunner in
# tests) where Rich falls back to an 80-column default.
CONSOLE_WIDTH = 100

_STATUS_SYMBOL: dict[str, str] = {"ok": "✓", "warn": "⚠", "error": "✗"}
_STATUS_COLOR: dict[str, str] = {"ok": "green", "warn": "yellow", "error": "red"}


def _component_status(check: ComponentCheck) -> str:
    symbol = _STATUS_SYMBOL[check.status]
    color = _STATUS_COLOR[check.status]
    text = f"{symbol} {check.detail}".strip() if check.detail else symbol
    return f"[{color}]{text}[/{color}]"


def _component_table(components: list[ComponentCheck]) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
    table.add_column("Component")
    table.add_column("Version")
    table.add_column("Status", no_wrap=False, overflow="fold")
    for check in components:
        table.add_row(check.name, check.version or "—", _component_status(check))
    return table


def _entity_status(check: EntityCheck) -> str:
    if check.enabled:
        return "[green]✓ enabled[/green]"
    return f"[red]✗ disabled — {check.reason}[/red]"


def _entity_table(entities: list[EntityCheck]) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
    table.add_column("Entity")
    table.add_column("Detector")
    table.add_column("Status", overflow="fold")
    for check in entities:
        table.add_row(check.name, check.detector, _entity_status(check))
    return table


def _summary_line(report: DoctorReport) -> str:
    active = sum(1 for e in report.entities if e.enabled)
    total = len(report.entities)
    disabled_note = "" if active == total else f" {total - active} disabled."
    return f"{active} of {total} entities active.{disabled_note}"


def render_report(console: Console, report: DoctorReport) -> None:
    console.print("[bold]MaskFlow Doctor[/bold]")
    console.print(_component_table(report.components))
    console.print()
    console.print(_entity_table(report.entities))
    console.print()
    console.print(_summary_line(report))

    errors = report.error_count
    warnings = report.warning_count
    if errors == 0 and warnings == 0:
        console.print("[bold green]✓ All checks passed.[/bold green]")
    elif errors == 0:
        console.print(f"[bold yellow]⚠ Healthy with {warnings} warning(s).[/bold yellow]")
    else:
        console.print(
            f"[bold red]✗ Not fully healthy — {errors} error(s), {warnings} warning(s).[/bold red]"
        )


def make_console() -> Console:
    return Console(width=CONSOLE_WIDTH)
