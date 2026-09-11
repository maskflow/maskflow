"""Rich rendering for `maskflow bench --my-data`. Kept separate from
bench_cmd.py so the command body stays thin, same split as
doctor.py/doctor_render.py.

Only type-checked against maskflow-bench (TYPE_CHECKING guard below,
`from __future__ import annotations` keeps every annotation an
unevaluated string at runtime) -- this module never constructs a
PRFResult/AdapterRunResult itself, only duck-types over one handed in by
bench_cmd.py, so it never needs the optional [bench] extra installed just
to be imported (bench_cmd.py's own lazy import guards the actual need for
it)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from maskflow_bench.matching import PRFResult
    from maskflow_bench.runner import AdapterRunResult

# Same rationale as doctor_render.py's: a fixed width so output doesn't
# wrap unpredictably under a non-tty (CI logs, CliRunner in tests).
CONSOLE_WIDTH = 100


def _cell(prf: PRFResult | None, field: str) -> str:
    """'—' when the metric is undefined (matching.PRFResult.f1's own
    convention, see PR #97): no predictions and no gold for this type.
    A real measured zero renders as "0.0%", not "—"."""
    if prf is None:
        return "—"
    value = getattr(prf, field)
    return "—" if value is None else f"{value:.1%}"


def _results_table(canonical_labels: tuple[str, ...], result: AdapterRunResult) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
    table.add_column("Entity")
    table.add_column("Strict P", justify="right")
    table.add_column("Strict R", justify="right")
    table.add_column("Strict F1", justify="right")
    table.add_column("Partial P", justify="right")
    table.add_column("Partial R", justify="right")
    table.add_column("Partial F1", justify="right")
    for label in canonical_labels:
        strict = result.strict.get(label)
        partial = result.partial.get(label)
        table.add_row(
            label,
            _cell(strict, "precision"),
            _cell(strict, "recall"),
            _cell(strict, "f1"),
            _cell(partial, "precision"),
            _cell(partial, "recall"),
            _cell(partial, "f1"),
        )
    return table


def render_my_data_result(
    console: Console,
    num_docs: int,
    canonical_labels: tuple[str, ...],
    result: AdapterRunResult,
) -> None:
    console.print("[bold]MaskFlow bench --my-data[/bold]")
    console.print(f"{num_docs} document(s), {len(canonical_labels)} entity type(s) in your labels.")
    console.print()
    if not canonical_labels:
        console.print(
            '[yellow]No gold (value_class="positive") entities found -- nothing to '
            "score. Check your file against docs/bench.md's schema.[/yellow]"
        )
        return
    console.print(_results_table(canonical_labels, result))
    console.print()
    console.print(
        '[dim]"—" means undefined (no predictions and no gold for that type); '
        '"0.0%" is a measured zero. Strict = exact span match, partial = any overlap.[/dim]'
    )


def make_console() -> Console:
    return Console(width=CONSOLE_WIDTH)
