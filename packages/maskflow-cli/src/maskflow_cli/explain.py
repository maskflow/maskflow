"""Data assembly for `maskflow explain` -- compiles the resolved
.maskflowrc config, runs detect(return_rejected=True), and turns the
resulting Spans into renderable views. No Rich/Typer here, so this is
testable without a console; see explain_render.py for the console output
and commands/explain_cmd.py for the Typer command.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from maskflow_core.config.engine import compile_config
from maskflow_core.config.schema import RootConfig
from maskflow_core.detection import DEFAULT_MIN_CONFIDENCE, detect
from maskflow_core.entities import ExplanationStep, Span

# How much of a matched value maskflow explain shows by default -- never the
# whole thing unless --full is passed (CLAUDE.md rule 1: never print raw PII
# by default, even in a diagnostic tool).
TRUNCATE_LEN = 8


@dataclass(frozen=True)
class SpanView:
    entity_type: str
    score: float
    validated: bool
    start: int
    end: int
    display_text: str
    truncated: bool
    steps: tuple[ExplanationStep, ...]
    # None for a masked span; the entity's active threshold for a near miss.
    threshold: float | None = None


@dataclass(frozen=True)
class ExplainResult:
    text_length: int
    masked: list[SpanView]
    near_misses: list[SpanView]


def _display_text(text: str, full: bool) -> tuple[str, bool]:
    if full or len(text) <= TRUNCATE_LEN:
        return text, False
    return text[:TRUNCATE_LEN] + "…", True


def _view(span: Span, *, full: bool, threshold: float | None) -> SpanView:
    display_text, truncated = _display_text(span.text, full)
    return SpanView(
        entity_type=str(span.entity_type),
        score=span.score,
        validated=span.validated,
        start=span.start,
        end=span.end,
        display_text=display_text,
        truncated=truncated,
        steps=tuple(span.explanation),
        threshold=threshold,
    )


def suggested_threshold(score: float) -> float:
    """The largest multiple of 0.05 at or below `score` -- low enough that
    setting entities.<TYPE>.threshold to this value would have caught this
    exact span, with a small margin against float rounding."""
    return math.floor(score * 20) / 20


def run_explain(text: str, root_config: RootConfig, *, full: bool = False) -> ExplainResult:
    compiled = compile_config(root_config)

    accepted, rejected = detect(
        text,
        min_confidence=DEFAULT_MIN_CONFIDENCE,
        return_rejected=True,
        **compiled.detect_kwargs(),
    )

    masked = [_view(s, full=full, threshold=None) for s in accepted]
    near_misses = [
        _view(
            s,
            full=full,
            threshold=compiled.per_entity_threshold.get(s.entity_type, DEFAULT_MIN_CONFIDENCE),
        )
        for s in rejected
    ]
    return ExplainResult(text_length=len(text), masked=masked, near_misses=near_misses)
