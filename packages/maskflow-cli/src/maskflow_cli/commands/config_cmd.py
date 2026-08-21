"""`maskflow config validate` / `maskflow config show [--resolved]`."""

from __future__ import annotations

from pathlib import Path

import typer

from ..config.render import format_resolved, format_show
from ..config.resolve import ConfigResolutionError, ResolvedConfig, resolve_config

app = typer.Typer(help="Inspect and validate .maskflowrc configuration.")

_CONFIG_OPTION = typer.Option(
    None, "--config", help="Explicit config file path, bypassing project/user file discovery."
)
_SET_OPTION = typer.Option(
    [], "--set", help="Override a resolved value, e.g. --set entities.AADHAAR.threshold=0.7"
)


def _resolve_or_exit(config: Path | None, overrides: list[str]) -> ResolvedConfig:
    try:
        return resolve_config(config_path_override=config, cli_sets=list(overrides))
    except ConfigResolutionError as exc:
        for line in str(exc).splitlines():
            typer.echo(line, err=True)
        raise typer.Exit(code=1) from exc


@app.command("validate")
def validate(
    config: Path | None = _CONFIG_OPTION,
    set_: list[str] = _SET_OPTION,
) -> None:
    """Validate the resolved .maskflowrc, reporting every problem found."""
    resolved = _resolve_or_exit(config, set_)

    for warning in resolved.warnings:
        typer.echo(f"WARNING: {warning.message}", err=True)

    sources = []
    if resolved.user_file is not None:
        sources.append(f"user file: {resolved.user_file}")
    if resolved.project_file is not None:
        sources.append(f"project file: {resolved.project_file}")
    suffix = f" ({', '.join(sources)})" if sources else " (no config file found -- using defaults)"
    typer.echo(f"Config is valid.{suffix}")


@app.command("show")
def show(
    resolved: bool = typer.Option(
        False, "--resolved", help="Annotate every value with where it came from."
    ),
    config: Path | None = _CONFIG_OPTION,
    set_: list[str] = _SET_OPTION,
) -> None:
    """Print the merged, validated config -- plain TOML by default, or one
    annotated `path = value (origin)` line per field with --resolved."""
    resolved_config = _resolve_or_exit(config, set_)

    if resolved:
        typer.echo(format_resolved(resolved_config))
    else:
        typer.echo(format_show(resolved_config), nl=False)
