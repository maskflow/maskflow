"""Render the split-screen demo SVG from two captured sessions.

    python render_svg.py off.json on.json kyc.db out.svg

Left: the session without the guard. Right: the same task with
maskflow-agent. Every command and value shown is taken from the captures
(capture.py) -- nothing is typed in by hand. Values that exist in the demo
database (all SYNTHETIC, see make_db.py) are highlighted red wherever the
model saw them; placeholders are highlighted green.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import textwrap
from html import escape
from typing import Any

W, H = 1280, 720
PANEL_W = 600
LEFT_X, RIGHT_X = 30, 650
TOP = 132
LINE = 22
CHARS = 60
LOOP = 18.0  # seconds

BG, PANEL, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, DIM = "#e6edf3", "#8b949e"
RED, GREEN, BLUE, AMBER = "#ff7b72", "#3fb950", "#79c0ff", "#d29922"
BOLD = ' font-weight="700"'
PLACEHOLDER = re.compile(r"<[A-Z][A-Z_]*_\d+>")


def _row(db: str, row_id: int) -> dict[str, str]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    found = conn.execute("SELECT * FROM kyc WHERE id = ?", (row_id,)).fetchone()
    return {k: str(found[k]) for k in found.keys()} if found else {}


def _db_values(db: str) -> dict[str, str]:
    conn = sqlite3.connect(db)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(kyc)")]
    out: dict[str, str] = {}
    for row in conn.execute("SELECT * FROM kyc"):
        for col, value in zip(cols, row, strict=True):
            if col in ("name", "aadhaar", "pan", "mobile", "upi"):
                out[str(value)] = col
    return out


def _spans(line: str, raw: dict[str, str]) -> list[tuple[str, str]]:
    """Split a line into (text, colour) runs: raw DB values red, placeholders green."""
    marks: list[tuple[int, int, str]] = [
        (m.start(), m.end(), GREEN) for m in PLACEHOLDER.finditer(line)
    ]
    for value in raw:
        start = line.find(value)
        while start != -1:
            marks.append((start, start + len(value), RED))
            start = line.find(value, start + 1)
    marks.sort()
    runs, cursor = [], 0
    for start, end, colour in marks:
        if start < cursor:
            continue
        runs.append((line[cursor:start], ""))
        runs.append((line[start:end], colour))
        cursor = end
    runs.append((line[cursor:], ""))
    return [r for r in runs if r[0]]


FIELDS = ("name", "aadhaar", "pan", "mobile", "upi")
PLACEHOLDER_TYPE = {
    "name": "PERSON_NAME",
    "aadhaar": "AADHAAR",
    "pan": "PAN",
    "mobile": "INDIAN_MOBILE",
    "upi": "UPI_VPA",
}


def _seen_fields(result: str, raw: dict[str, str], row_values: dict[str, str]) -> list[str]:
    """Format-agnostic: for each sensitive field of the looked-up record, what
    the model actually received -- the real value if it is in the output,
    else the placeholder of that type found in the output."""
    # The record's own output line (first cell == its id), so a query that
    # returned several rows doesn't show another customer's placeholders.
    record_id = row_values.get("id", "")
    for candidate in result.splitlines():
        first = re.split(r"[|,\s]+", candidate.strip(" |"), maxsplit=1)[0]
        if record_id and first == record_id:
            result = candidate
            break
    lines = []
    for field in FIELDS:
        value = row_values.get(field, "")
        if value and value in result:
            shown = value
        else:
            match = re.search(rf"<{PLACEHOLDER_TYPE[field]}_\d+>", result)
            if not match:
                continue
            shown = match.group(0)
        lines.append(f"    {field:<8} {shown}")
    return lines


def _panel_lines(
    data: dict[str, Any], raw: dict[str, str], row_values: dict[str, str]
) -> list[tuple[str, str]]:
    """(text, base colour) lines for one panel."""
    lines: list[tuple[str, str]] = []
    for chunk in textwrap.wrap(data["prompt"], CHARS - 2):
        lines.append(("> " + chunk if not lines else "  " + chunk, TEXT))
    lines.append(("", TEXT))
    for step in data["steps"]:
        for i, chunk in enumerate(textwrap.wrap(step["command"], CHARS - 2)):
            lines.append((("$ " if i == 0 else "  ") + chunk, BLUE))
        if "UPDATE" in step["command"].upper():
            status = "verified" if "verified" in step["result"] else "?"
            lines.append((f"  -> row updated, status = {status}", GREEN))
        else:
            seen = _seen_fields(step["result"], raw, row_values)
            if seen:
                lines.append(("  the model received:", DIM))
                lines += [(line, TEXT) for line in seen]
        lines.append(("", TEXT))
    return lines


def _leaked(data: dict[str, Any], raw: dict[str, str]) -> list[str]:
    seen = json.dumps(data["steps"])
    return sorted({col for value, col in raw.items() if value in seen})


def _render_lines(
    x: int, lines: list[tuple[str, str]], raw: dict[str, str], t0: float
) -> list[str]:
    out = []
    for i, (text, base) in enumerate(lines):
        y = TOP + i * LINE
        delay = t0 + i * 0.45
        tspans = "".join(
            f'<tspan fill="{colour or base}"{BOLD if colour else ""}>{escape(run)}</tspan>'
            for run, colour in _spans(text, raw)
        )
        out.append(
            f'<text class="l" x="{x + 18}" y="{y}" style="animation-delay:{delay:.2f}s">'
            f"{tspans}</text>"
        )
    return out


def render(off: dict[str, Any], on: dict[str, Any], db: str) -> str:
    raw = _db_values(db)
    record = _row(db, 4)
    left, right = _panel_lines(off, raw, record), _panel_lines(on, raw, record)
    leaked_off, leaked_on = _leaked(off, raw), _leaked(on, raw)
    n = max(len(left), len(right))
    summary_t = 0.6 + n * 0.45

    def verdict(leaked: list[str]) -> tuple[str, str]:
        if leaked:
            return f"Sent to the model: {', '.join(leaked)}", RED
        return "Sent to the model: no personal data. Row updated.", GREEN

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-label="Split-screen demo: the same Claude '
        f"Code task on a KYC table without and with maskflow-agent. Without it the model "
        f"receives Aadhaar, PAN, mobile and UPI values; with it the model sees only "
        f'placeholders and still updates the right row.">',
        "<title>maskflow-agent demo</title>",
        "<style>",
        f"text{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:15px;fill:{TEXT}}}",
        "text{white-space:pre}",
        ".h{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif}",
        f".l{{opacity:0;animation:show {LOOP}s infinite}}",
        "@keyframes show{0%{opacity:0}3%{opacity:1}92%{opacity:1}100%{opacity:0}}",
        "@media (prefers-reduced-motion: reduce){.l{animation:none;opacity:1}}",
        "</style>",
        f'<rect width="{W}" height="{H}" rx="14" fill="{BG}"/>',
        f'<text class="h" x="{W // 2}" y="44" text-anchor="middle" font-size="22" '
        f'font-weight="700" fill="{TEXT}">Same task. Same data. One of them leaks it.</text>',
    ]
    for x, title, colour in (
        (LEFT_X, "Claude Code", RED),
        (RIGHT_X, "Claude Code + maskflow-agent", GREEN),
    ):
        parts.append(
            f'<rect x="{x}" y="70" width="{PANEL_W}" height="{H - 150}" rx="10" '
            f'fill="{PANEL}" stroke="{BORDER}"/>'
        )
        parts.append(f'<circle cx="{x + 22}" cy="92" r="6" fill="{colour}"/>')
        parts.append(
            f'<text class="h" x="{x + 38}" y="97" font-size="16" font-weight="600" '
            f'fill="{TEXT}">{escape(title)}</text>'
        )
    parts += _render_lines(LEFT_X, left, raw, 0.6)
    parts += _render_lines(RIGHT_X, right, raw, 0.6)
    for x, (label, colour) in ((LEFT_X, verdict(leaked_off)), (RIGHT_X, verdict(leaked_on))):
        parts.append(
            f'<text class="l h" x="{x + 18}" y="{H - 100}" font-size="17" font-weight="700" '
            f'fill="{colour}" style="animation-delay:{summary_t:.2f}s">{escape(label)}</text>'
        )
    parts.append(
        f'<text class="h" x="{W // 2}" y="{H - 34}" text-anchor="middle" font-size="16" '
        f'fill="{DIM}">pip install maskflow-agent  ·  maskflow-agent install  ·  '
        f"synthetic data, real Claude Code sessions</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    off_path, on_path, db_path, out_path = sys.argv[1:5]
    with open(off_path, encoding="utf-8") as f:
        off_data = json.load(f)
    with open(on_path, encoding="utf-8") as f:
        on_data = json.load(f)
    svg = render(off_data, on_data, db_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out_path}")
