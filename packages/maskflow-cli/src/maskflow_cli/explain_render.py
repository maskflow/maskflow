"""Rich rendering for `maskflow explain`. Kept separate from explain.py's
pure data assembly so the view-building logic is testable without a
console."""

from __future__ import annotations

from maskflow_core.entities import ExplanationStep
from rich.console import Console

from .explain import ExplainResult, SpanView, suggested_threshold

# Fixed width for the same reason as doctor_render.py: predictable wrapping
# under a non-tty (CI logs, CliRunner in tests).
CONSOLE_WIDTH = 100


def _format_delta(delta: float) -> str:
    return f"+{delta}" if delta >= 0 else str(delta)


def _step_line(step: ExplanationStep) -> str:
    if step.rule.startswith(("pattern:", "ner:")):
        return f"{step.rule} {step.outcome}"
    if step.rule == "checksum":
        return f"checksum {step.outcome} ({_format_delta(step.delta)})"
    if step.rule == "context":
        if step.outcome == "not_configured":
            return "context: no context keywords configured for this entity"
        if step.outcome == "boosted":
            return f"context: {step.detail} ({_format_delta(step.delta)})"
        return f"context: {step.detail}"
    if step.rule == "threshold":
        return f"threshold: {step.detail}"
    if step.rule == "overlap:contained":
        return f"overlap: preferred {step.detail}"
    if step.rule == "merge":
        return f"merge: {step.detail}"
    return f"{step.rule}: {step.outcome} {step.detail}".strip()


def _render_span(console: Console, label: str, view: SpanView) -> None:
    header = f"[{label}] {view.entity_type:<16} score {view.score:.2f}   "
    if view.threshold is not None:
        header += f"threshold {view.threshold:.2f}   "
    else:
        header += f"validated {'✓' if view.validated else '—'}   "
    header += f"span {view.start}:{view.end}"
    # markup=False: `header`/`match_line`/step text are literal (may contain
    # bracket labels like "[a]" or an actual matched value) -- Rich's markup
    # parser would otherwise try to interpret "[a]" as a style tag and drop it.
    console.print(header, markup=False)

    match_line = f'    match  "{view.display_text}"'
    if view.truncated:
        match_line += "   (--full to show entire match)"
    console.print(match_line, markup=False)

    for step in view.steps:
        if step.rule == "threshold":
            continue  # rendered as the closing "dropped --" line instead
        console.print(f"    │ {_step_line(step)}", markup=False)

    if view.threshold is not None:
        console.print(
            f"    └ [red]dropped — score {view.score:.2f} < threshold {view.threshold:.2f}[/red]"
        )
    else:
        console.print("    └ [green]masked[/green]")
    console.print()


def _render_fixit(console: Console, view: SpanView) -> None:
    assert view.threshold is not None
    suggestion = suggested_threshold(view.score)
    console.print(
        f"    Not detected: {view.entity_type} scored {view.score:.2f}, "
        f"below threshold {view.threshold:.2f}."
    )
    console.print("    To catch it, add to .maskflowrc (project root):\n")
    console.print(f"        [entities.{view.entity_type}]", markup=False)
    console.print(f"        threshold = {suggestion:g}")
    console.print()


def render_explain(console: Console, result: ExplainResult) -> None:
    if not result.masked and not result.near_misses:
        console.print(f"Analyzed {result.text_length} chars. No PII detected.")
        return

    near_miss_word = "near miss" if len(result.near_misses) == 1 else "near misses"
    console.print(
        f"Analyzed {result.text_length} chars. "
        f"{len(result.masked)} span(s) masked, {len(result.near_misses)} {near_miss_word}.\n"
    )

    for i, view in enumerate(result.masked, start=1):
        _render_span(console, str(i), view)

    if result.near_misses:
        console.print("[bold]NEAREST MISSES[/bold] — below threshold, not masked\n")
        for i, view in enumerate(result.near_misses):
            label = chr(ord("a") + i)
            _render_span(console, label, view)
            _render_fixit(console, view)

    console.print(
        f"{len(result.masked)} span(s) masked · {len(result.near_misses)} near miss(es) shown "
        "· no raw PII written to any log"
    )


def make_console() -> Console:
    return Console(width=CONSOLE_WIDTH)
