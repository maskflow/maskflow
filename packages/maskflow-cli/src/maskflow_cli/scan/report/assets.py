"""Inline CSS/JS for the HTML report. Kept as plain strings (not a template
file) so the report is provably self-contained: there is nothing to fetch,
bundle, or path-resolve at render time.

Design system: accent #0E6B4F, masked tokens mono + #B45309, system fonts,
generous whitespace, print-clean.
"""

from __future__ import annotations

CSS = """
:root {
  --accent: #0E6B4F;
  --accent-tint: #E7F1EC;
  --token: #B45309;
  --ink: #1A1F1D;
  --muted: #5B6763;
  --line: #DCE3E0;
  --bg: #FFFFFF;
  --crit: #9A2B2B; --high: #B45309; --med: #1F6FaB; --low: #5B6763;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.6 ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 880px; margin: 0 auto; padding: 56px 28px 96px; }
h1, h2, h3 { line-height: 1.25; font-weight: 650; letter-spacing: -0.01em; }
h1 { font-size: 30px; margin: 0 0 4px; }
h2 { font-size: 21px; margin: 56px 0 16px; padding-top: 20px; border-top: 1px solid var(--line); }
h3 { font-size: 16px; margin: 28px 0 10px; }
p { margin: 0 0 14px; }
a { color: var(--accent); }
.muted { color: var(--muted); }
.small { font-size: 13.5px; }
code, .token, .mono {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.92em;
}
.token { color: var(--token); font-weight: 600; white-space: nowrap; }

header.doc { margin-bottom: 8px; }
.brand { display: flex; align-items: baseline; gap: 10px; }
.brand .name { font-weight: 700; color: var(--accent); letter-spacing: -0.02em; font-size: 18px; }
.trust {
  margin-top: 18px; padding: 10px 14px; background: var(--accent-tint);
  border-radius: 8px; color: var(--accent); font-weight: 600; font-size: 14px;
}
.scope { margin-top: 14px; }

.headline { margin: 40px 0 8px; }
.headline .n {
  font-size: 76px; font-weight: 700; letter-spacing: -0.03em; color: var(--accent);
  line-height: 1;
}
.headline .cap { font-size: 17px; margin-top: 10px; max-width: 62ch; }
.est-flag {
  display: inline-block; margin-left: 8px; padding: 1px 7px; border-radius: 999px;
  background: #FBEEDD; color: var(--token); font-size: 11.5px; font-weight: 700;
  vertical-align: middle; letter-spacing: 0.02em;
}

table { border-collapse: collapse; width: 100%; font-size: 14px; margin: 8px 0 4px; }
th, td {
  text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top;
}
th {
  font-weight: 650; color: var(--muted); font-size: 12.5px;
  text-transform: uppercase; letter-spacing: 0.04em;
}
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:last-child td { border-bottom: none; }

.pill {
  display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 12px;
  font-weight: 700; color: #fff; letter-spacing: 0.02em;
}
.pill.Critical { background: var(--crit); }
.pill.High { background: var(--high); }
.pill.Medium { background: var(--med); }
.pill.Low { background: var(--low); }

.chart { margin: 6px 0 18px; }
.bar-row {
  display: grid; grid-template-columns: 180px 1fr 68px; gap: 10px;
  align-items: center; margin: 4px 0; font-size: 13.5px;
}
.bar-row .label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { background: var(--line); border-radius: 3px; height: 14px; overflow: hidden; }
.bar-fill { background: var(--accent); height: 100%; }
.bar-row .val { text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }

.spark { display: block; width: 100%; height: 120px; }
.spark rect { fill: var(--accent); }
.spark .axis { stroke: var(--line); stroke-width: 1; }

details.sev { border: 1px solid var(--line); border-radius: 8px; margin: 8px 0; padding: 0; }
details.sev > summary {
  list-style: none; cursor: pointer; padding: 12px 14px; display: grid;
  grid-template-columns: 84px 1fr auto; gap: 12px; align-items: center;
}
details.sev > summary::-webkit-details-marker { display: none; }
details.sev .why { font-size: 13.5px; color: var(--muted); }
details.sev .body { padding: 4px 14px 14px; border-top: 1px solid var(--line); }
.excerpt {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 12.5px; background: #F7F9F8; border-radius: 6px; padding: 8px 10px;
  margin: 6px 0; white-space: pre-wrap; word-break: break-word;
}
.excerpt .token { color: var(--token); font-weight: 700; }

.appendix {
  border: 1px dashed var(--line); border-radius: 8px; padding: 16px 18px; background: #FAFBFB;
}
footer.doc {
  margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--line);
  font-size: 12.5px; color: var(--muted);
}
footer.doc dl {
  display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 8px 0;
}
footer.doc dt { font-weight: 650; }

@media print {
  .wrap { max-width: none; padding: 0 12mm; }
  h2 { break-before: auto; }
  details.sev { break-inside: avoid; }
  details.sev[open] > summary { pointer-events: none; }
  a { color: var(--ink); text-decoration: none; }
  .trust { border: 1px solid var(--accent); }
}
"""

# The only script: an "expand all" convenience for the severity section.
# The report is fully readable and navigable with JS disabled (native
# <details>), so this is enhancement, not a dependency.
JS = """
(function () {
  var btn = document.getElementById('expand-all');
  if (!btn) return;
  var open = false;
  btn.addEventListener('click', function () {
    open = !open;
    document.querySelectorAll('details.sev').forEach(function (d) { d.open = open; });
    btn.textContent = open ? 'Collapse all' : 'Expand all';
  });
})();
"""
