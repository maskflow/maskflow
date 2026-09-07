"""`maskflow explain "<text>"`."""

from __future__ import annotations

from pathlib import Path

import typer
from maskflow_core.config.resolve import ConfigResolutionError, resolve_config

from ..evidence import emit_explain_evidence
from ..explain import build_explain_result, detect_for_explain
from ..explain_render import make_console, render_explain

_CONFIG_OPTION = typer.Option(
    None, "--config", help="Explicit config file path, bypassing project/user file discovery."
)
_SET_OPTION = typer.Option(
    [], "--set", help="Override a resolved value, e.g. --set entities.SSN.threshold=0.3"
)
_FULL_OPTION = typer.Option(
    False, "--full", help="Show the entire matched value instead of truncating to 8 chars."
)
_EVIDENCE_OPTION = typer.Option(
    None,
    "--evidence/--no-evidence",
    help="Emit metadata-only evidence events for this run (default: the "
    "[evidence] section of your .maskflowrc). Never contains a detected value.",
)
_EVIDENCE_FILE_OPTION = typer.Option(
    None,
    "--evidence-file",
    help="Write evidence events (one JSON object per line) to this file. Implies --evidence.",
)


def explain(
    text: str = typer.Argument(..., help="Text to analyze -- never written to any log."),
    full: bool = _FULL_OPTION,
    config: Path | None = _CONFIG_OPTION,
    set_: list[str] = _SET_OPTION,
    evidence: bool | None = _EVIDENCE_OPTION,
    evidence_file: Path | None = _EVIDENCE_FILE_OPTION,
) -> None:
    """Show, span by span, why each piece of text was (or wasn't) detected
    as PII: the pattern/NER hit, checksum result, context boost, and the
    threshold decision behind it. Spans that scored below their entity's
    threshold are listed separately as NEAREST MISSES, with the
    .maskflowrc change that would catch them."""
    try:
        resolved = resolve_config(config_path_override=config, cli_sets=list(set_))
    except ConfigResolutionError as exc:
        for line in str(exc).splitlines():
            typer.echo(line, err=True)
        raise typer.Exit(code=1) from exc

    accepted, rejected = detect_for_explain(text, resolved.config)
    result = build_explain_result(text, accepted, rejected, resolved.config, full=full)
    render_explain(make_console(), result)

    enabled = resolved.config.evidence.enabled if evidence is None else evidence
    emitted = emit_explain_evidence(
        accepted,
        rejected,
        resolved.config,
        enabled=enabled,
        evidence_file=evidence_file,
    )
    if emitted and evidence_file is not None:
        typer.echo(f"\n{emitted} evidence event(s) written to {evidence_file}", err=True)
