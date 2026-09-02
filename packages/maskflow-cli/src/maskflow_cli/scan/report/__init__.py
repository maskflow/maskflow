"""Report building and rendering for `maskflow scan`."""

from __future__ import annotations

from .build import build_summary
from .csv_out import render_csv
from .html import render_html
from .json_out import render_json
from .summary import ScanSummary

RENDERERS = {
    "html": render_html,
    "json": render_json,
    "csv": render_csv,
}


def render(summary: ScanSummary, fmt: str) -> str:
    try:
        return RENDERERS[fmt](summary)
    except KeyError:
        raise ValueError(f"unknown format {fmt!r}; choose html, json, or csv") from None


__all__ = ["build_summary", "render", "render_html", "render_json", "render_csv", "ScanSummary"]
