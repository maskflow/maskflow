"""`maskflow bench --my-data <path>` -- scores MaskFlow's own detector
against a user's own labelled documents and prints per-entity
precision/recall/F1. Not a comparison tool (see docs/bench.md); the
multi-adapter comparison against Presidio/mask-privacy/etc. that produced
the published IndiaPII-Bench figures lives in bench/ (repo dev tooling).

`maskflow-bench` is an **optional** dependency (`pip install
'maskflow-cli[bench]'`) -- imported lazily here, same policy as
`maskflow_cli.evidence`, so a bare CLI install (and the standalone
PyInstaller binary) doesn't require it and every other command runs
without it.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..bench_render import make_console, render_my_data_result

_MISSING = (
    "`maskflow bench` needs the bench extra -- install it with: pip install 'maskflow-cli[bench]'"
)

_MY_DATA_OPTION = typer.Option(
    ..., "--my-data", exists=True, dir_okay=False, help="Path to your labelled JSONL file."
)
_OUT_OPTION = typer.Option(
    None, "--out", help="Directory to also write results.json and results.md into."
)
_LIMIT_OPTION = typer.Option(
    None, "--limit", help="Score only the first N documents (useful to smoke-test a large file)."
)


def bench(
    my_data: Path = _MY_DATA_OPTION,
    out: Path | None = _OUT_OPTION,
    limit: int | None = _LIMIT_OPTION,
) -> None:
    """Runs MaskFlow's detector over your own labelled JSONL file and
    reports per-entity precision/recall/F1 under both strict-span and
    partial-overlap matching. See docs/bench.md for the file schema."""
    try:
        from maskflow_bench.loader import LoaderError
        from maskflow_bench.report import write_report
        from maskflow_bench.scorer import score_my_data
    except ModuleNotFoundError as exc:
        typer.echo(_MISSING, err=True)
        raise typer.Exit(code=1) from exc

    console = make_console()
    try:
        num_docs, labels, result = score_my_data(my_data, limit=limit)
    except LoaderError as exc:
        typer.echo(f"{my_data}:{exc}", err=True)
        raise typer.Exit(code=1) from exc

    if num_docs == 0:
        typer.echo(f"{my_data}: no documents found -- is the file empty?", err=True)
        raise typer.Exit(code=1)

    render_my_data_result(console, num_docs, labels, result)

    if out is not None:
        write_report(out, "my-data", num_docs, labels, {"maskflow": result})
        console.print(f"\nwrote {out / 'results.json'} and {out / 'results.md'}")
