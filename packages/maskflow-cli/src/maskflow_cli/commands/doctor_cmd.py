"""`maskflow doctor`."""

from __future__ import annotations

import typer

from ..doctor import run_checks
from ..doctor_render import make_console, render_report


def doctor() -> None:
    """Check installed versions, spaCy model presence, and .maskflowrc
    validity, and report which entities are consequently enabled/disabled.
    Exits 0 only when every check passes."""
    console = make_console()
    report = run_checks()
    render_report(console, report)

    if not report.healthy:
        raise typer.Exit(code=1)
