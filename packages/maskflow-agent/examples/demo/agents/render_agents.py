"""Render the multi-agent demo: one animated SVG clip per agent, plus an
intro and an outro card for the montage.

    python render_agents.py <out-dir>

Each clip shows, left, the synthetic customers.csv on disk (real values in
red) and, right, what that agent sent to its model in a live session (the
masked row in green, then the agent's own answer). The agent data comes
from agents.json, and every quoted line is taken from that agent's session
record. All identifiers are SYNTHETIC (see customers.csv).

Logos: simple-icons (CC0); the marks belong to their owners and are shown
only to indicate compatibility. Agents without a published mark get a text
wordmark.
"""

# ruff: noqa: E501  -- SVG markup strings read better unbroken.
from __future__ import annotations

import json
import re
import sys
from html import escape
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
W, H = 1280, 720
BG, PANEL, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, DIM = "#e6edf3", "#8b949e"
RED, GREEN, BLUE = "#ff7b72", "#3fb950", "#79c0ff"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SANS = "-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
PLACEHOLDER = re.compile(r"<[A-Z][A-Z_]*_\d+>")
CLIP_SECONDS = 7.0  # animation length; the recorder holds the last frame


def _style() -> str:
    return (
        "<style>"
        f"svg{{font-family:{MONO};font-size:17px;fill:{TEXT}}}"
        "text{white-space:pre}"
        f".s{{font-family:{SANS}}}"
        ".a{opacity:0;animation:in .45s ease-out forwards}"
        "@keyframes in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}"
        "@media (prefers-reduced-motion: reduce){.a{animation:none;opacity:1}}"
        "</style>"
    )


def _logo(name: str | None, x: int, y: int, size: int, fill: str = TEXT) -> str:
    """The brand mark as a white glyph, or '' when there is none."""
    if not name:
        return ""
    svg = (HERE / "logos" / f"{name}.svg").read_text(encoding="utf-8")
    path = re.search(r'<path d="([^"]+)"', svg)
    if not path:
        return ""
    scale = size / 24
    return (
        f'<path d="{path.group(1)}" fill="{fill}" '
        f'transform="translate({x},{y}) scale({scale:.4f})"/>'
    )


def _runs(line: str, raw: set[str], base: str) -> str:
    """tspans: raw synthetic values red+bold, placeholders green+bold."""
    marks = [(m.start(), m.end(), GREEN) for m in PLACEHOLDER.finditer(line)]
    for value in raw:
        i = line.find(value)
        while i != -1:
            marks.append((i, i + len(value), RED))
            i = line.find(value, i + 1)
    marks.sort()
    out, cursor = [], 0
    for start, end, colour in marks:
        if start < cursor:
            continue
        out.append(f'<tspan fill="{base}">{escape(line[cursor:start])}</tspan>')
        out.append(f'<tspan fill="{colour}" font-weight="700">{escape(line[start:end])}</tspan>')
        cursor = end
    out.append(f'<tspan fill="{base}">{escape(line[cursor:])}</tspan>')
    return "".join(out)


def _text(
    x: int, y: int, line: str, raw: set[str], base: str, delay: float, extra: str = ""
) -> str:
    return (
        f'<text class="a" x="{x}" y="{y}" style="animation-delay:{delay:.2f}s"{extra}>'
        f"{_runs(line, raw, base)}</text>"
    )


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(" "), [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + ([cur] if cur else [])


def _csv() -> tuple[list[str], set[str], str]:
    lines = (HERE / "customers.csv").read_text(encoding="utf-8").splitlines()
    header = next(line for line in lines if line.startswith("id,"))
    row = next(line for line in lines if line.startswith("1,"))
    cols = dict(zip(header.split(","), row.split(","), strict=True))
    raw = {cols["aadhaar"], cols["pan"], cols["mobile"]}
    masked = f"1,{cols['name']},<AADHAAR_1>,<PAN_1>,<INDIAN_MOBILE_1>"
    return [header, row], raw, masked


def clip(agent: dict[str, Any], prompt: str) -> str:
    (header, row), raw, masked = _csv()
    lx, rx, top, pw = 40, 470, 150, 770
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{escape(agent["name"])} with maskflow-agent: the CSV on disk holds '
        f'real (synthetic) identifiers; the model received only placeholders.">',
        _style(),
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
    ]
    # header
    logo = _logo(agent["logo"], 40, 34, 40) or _terminal_icon(40, 34, 40)
    name_x = 96
    parts.append(
        f'<g class="a">{logo}<text class="s" x="{name_x}" y="68" font-size="34" '
        f'font-weight="700">{escape(agent["name"])}<tspan fill="{DIM}" font-weight="400">'
        f"  +  maskflow-agent</tspan></text></g>"
    )
    badge = f"verified live · {agent['version']}"
    bw = 22 + len(badge) * 8.6
    parts.append(
        f'<g class="a" style="animation-delay:.3s"><rect x="{W - 40 - bw:.0f}" y="40" width="{bw:.0f}" '
        f'height="34" rx="17" fill="#12261a" stroke="{GREEN}"/><text class="s" x="{W - 40 - bw / 2:.0f}" '
        f'y="62" text-anchor="middle" font-size="15" fill="{GREEN}">{escape(badge)}</text></g>'
    )
    # panels
    for x, w, title, colour, delay in (
        (lx, 400, "customers.csv on your disk", RED, 0.6),
        (rx, pw, f"what {agent['name']} sent to the model", GREEN, 1.2),
    ):
        parts.append(
            f'<g class="a" style="animation-delay:{delay}s"><rect x="{x}" y="100" width="{w}" '
            f'height="500" rx="12" fill="{PANEL}" stroke="{BORDER}"/>'
            f'<circle cx="{x + 24}" cy="126" r="6" fill="{colour}"/>'
            f'<text class="s" x="{x + 40}" y="132" font-size="17" font-weight="600">'
            f"{escape(title)}</text></g>"
        )
    # left: the file, one field per line so the raw values read clearly
    (_, name, aadhaar, pan, mobile) = row.split(",")
    left = [
        ("# synthetic test data", DIM),
        ("", TEXT),
        ("id 1", TEXT),
        (f"name     {name}", TEXT),
        (f"aadhaar  {aadhaar}", TEXT),
        (f"pan      {pan}", TEXT),
        (f"mobile   {mobile}", TEXT),
    ]
    for i, (line, base) in enumerate(left):
        parts.append(_text(lx + 24, top + 34 + i * 30, line, raw, base, 0.9 + i * 0.12))
    # right: prompt, command(s), what the model received, its answer
    y, t = top + 34, 1.6
    for i, chunk in enumerate(_wrap(f"> {prompt}", 66)):
        parts.append(_text(rx + 24, y, chunk if i == 0 else f"  {chunk}", raw, DIM, t))
        y += 28
    y += 18
    for step in agent["steps"]:
        blocked = step.startswith("BLOCKED")
        line = step if blocked else f"$ {step}"
        for chunk in _wrap(line, 66):
            t += 0.5
            parts.append(_text(rx + 24, y, chunk, raw, "#d29922" if blocked else BLUE, t))
            y += 30
    t += 0.6
    parts.append(
        _text(rx + 24, y + 6, "the model received:", raw, DIM, t, ' font-family="' + SANS + '"')
    )
    y += 40
    t += 0.4
    for line in (header, masked):
        parts.append(_text(rx + 24, y, line, raw, TEXT, t))
        y += 30
        t += 0.15
    if agent.get("answer"):
        t += 0.6
        y += 16
        parts.append(
            _text(
                rx + 24, y, f"{agent['name']} answered:", raw, DIM, t, ' font-family="' + SANS + '"'
            )
        )
        y += 34
        for chunk in _wrap(agent["answer"], 66):
            t += 0.25
            parts.append(_text(rx + 24, y, chunk, raw, TEXT, t))
            y += 30
    t += 0.7
    parts.append(
        f'<text class="a s" x="{rx + 24}" y="580" font-size="20" font-weight="700" fill="{GREEN}" '
        f'style="animation-delay:{t:.2f}s">Sent to the model: no personal data.</text>'
    )
    # footer
    parts.append(
        f'<text class="a" x="{W // 2}" y="660" text-anchor="middle" font-size="19" fill="{TEXT}" '
        f'style="animation-delay:{t + 0.3:.2f}s"><tspan fill="{DIM}">$ </tspan>pip install maskflow-agent'
        f'<tspan fill="{DIM}">  &amp;&amp;  </tspan>{escape(agent["install"])}</text>'
    )
    parts.append(
        f'<text class="s" x="{W // 2}" y="696" text-anchor="middle" font-size="13" fill="{DIM}">'
        f"Replayed from a real {escape(agent['name'])} session · synthetic data · {escape(agent['mode'])}</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _terminal_icon(x: int, y: int, size: int) -> str:
    """A neutral `>_` tile for agents without a published mark (no brand
    imitation)."""
    return (
        f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{size // 5}" fill="none" '
        f'stroke="{TEXT}" stroke-width="2.5"/><text x="{x + size // 2}" y="{y + size * 0.68:.0f}" '
        f'text-anchor="middle" font-size="{size // 2}" font-weight="700">&gt;_</text>'
    )


def _logo_row(agents: list[dict[str, Any]], y: int, delay: float) -> str:
    """All nine agents in one row: mark + name."""
    cells = []
    margin = 50
    gap = (W - 2 * margin) / len(agents)
    for i, agent in enumerate(agents):
        cx = int(margin + gap * i + gap / 2)
        logo = _logo(agent["logo"], cx - 18, y, 36)
        label = agent["name"].replace("Google ", "").replace("OpenAI ", "").replace("GitHub ", "")
        mark = logo or _terminal_icon(cx - 18, y, 36)
        cells.append(
            f'<g class="a" style="animation-delay:{delay + i * 0.12:.2f}s">{mark}'
            f'<text class="s" x="{cx}" y="{y + 66}" text-anchor="middle" font-size="14" '
            f'fill="{DIM}">{escape(label)}</text></g>'
        )
    return "".join(cells)


def intro(agents: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            _style(),
            f'<rect width="{W}" height="{H}" fill="{BG}"/>',
            f'<text class="a s" x="{W // 2}" y="200" text-anchor="middle" font-size="46" font-weight="800">'
            "Your coding agent just read</text>",
            f'<text class="a s" x="{W // 2}" y="260" text-anchor="middle" font-size="46" font-weight="800" '
            f'style="animation-delay:.3s">your customers&#8217; <tspan fill="{RED}">Aadhaar numbers</tspan>.</text>',
            f'<text class="a s" x="{W // 2}" y="340" text-anchor="middle" font-size="30" fill="{GREEN}" '
            'style="animation-delay:1.4s">maskflow-agent keeps them out of the model.</text>',
            _logo_row(agents, 430, 2.0),
            "</svg>\n",
        ]
    )


def outro(agents: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            _style(),
            f'<rect width="{W}" height="{H}" fill="{BG}"/>',
            f'<text class="a s" x="{W // 2}" y="170" text-anchor="middle" font-size="40" font-weight="800">'
            "One guard. Nine coding agents. Verified live.</text>",
            _logo_row(agents, 230, 0.4),
            f'<text class="a" x="{W // 2}" y="420" text-anchor="middle" font-size="30" '
            f'style="animation-delay:1.8s"><tspan fill="{DIM}">$ </tspan>pip install maskflow-agent</text>',
            f'<text class="a s" x="{W // 2}" y="490" text-anchor="middle" font-size="22" fill="{DIM}" '
            'style="animation-delay:2.3s">Aadhaar · PAN · UPI · mobile · bank accounts · names  —  '
            "masked before the model sees them</text>",
            f'<text class="a s" x="{W // 2}" y="580" text-anchor="middle" font-size="34" font-weight="700" '
            f'fill="{GREEN}" style="animation-delay:2.8s">maskflow.in/agents</text>',
            f'<text class="a s" x="{W // 2}" y="630" text-anchor="middle" font-size="16" fill="{DIM}" '
            'style="animation-delay:3.1s">MIT · runs locally · no telemetry</text>',
            "</svg>\n",
        ]
    )


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads((HERE / "agents.json").read_text(encoding="utf-8"))
    for agent in data["agents"]:
        (out / f"{agent['slug']}.svg").write_text(clip(agent, data["prompt"]), encoding="utf-8")
    (out / "intro.svg").write_text(intro(data["agents"]), encoding="utf-8")
    (out / "outro.svg").write_text(outro(data["agents"]), encoding="utf-8")
    print(f"wrote {len(data['agents'])} clips + intro + outro to {out}")
