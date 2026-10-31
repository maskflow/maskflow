"""Inline CSS/JS for the audit report.

Kept as plain strings (not a template file) so the report is provably
self-contained: there is nothing to fetch, bundle, or path-resolve at
render time -- it can be emailed to an auditor on a locked-down machine.
Same reasoning, and the same design system, as maskflow-cli's scan report:
accent #0E6B4F, mono + #B45309 for anything machine-ish, system fonts,
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
  --leak: #9A2B2B; --unmasked: #B45309; --unknown: #1F6FaB; --ok: #0E6B4F;
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
.brand { font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
h1 { font-size: 30px; line-height: 1.25; margin: 6px 0 10px; }
h2 {
  font-size: 19px; margin: 44px 0 12px; padding-top: 20px;
  border-top: 1px solid var(--line);
}
h3 { font-size: 15px; margin: 22px 0 6px; }
p { margin: 8px 0; }
.small { font-size: 13.5px; }
.muted { color: var(--muted); }
.mono {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 12.5px;
}
.trust {
  border: 1px solid var(--accent); background: var(--accent-tint);
  border-radius: 8px; padding: 12px 14px; margin: 16px 0; font-size: 14px;
}
.scope { font-size: 13.5px; color: var(--muted); }

.headline { margin: 28px 0 8px; }
.headline .n { font-size: 76px; line-height: 1; font-weight: 700; color: var(--accent); }
.headline .cap { font-size: 16px; margin-top: 6px; }
.flag {
  display: inline-block; font-size: 12px; font-weight: 650; padding: 2px 8px;
  border-radius: 999px; background: var(--leak); color: #fff; margin-left: 8px;
}
.flag.warn { background: var(--unmasked); }
.flag.info { background: var(--unknown); }

.bars { display: grid; gap: 6px; margin: 10px 0 4px; }
.bar { display: grid; grid-template-columns: 180px 1fr 68px; gap: 12px; align-items: center; }
.bar .label { font-size: 13.5px; }
.bar .track { background: #EFF3F1; border-radius: 4px; height: 14px; overflow: hidden; }
.bar .fill { background: var(--accent); height: 100%; }
.bar .n { font-size: 13px; text-align: right; color: var(--muted); }

details.flow { border: 1px solid var(--line); border-radius: 8px; margin: 8px 0; padding: 0; }
details.flow.leak { border-color: var(--leak); border-left-width: 4px; }
details.flow > summary {
  list-style: none; cursor: pointer; padding: 12px 14px; display: grid;
  grid-template-columns: 116px 1fr auto; gap: 12px; align-items: center;
}
details.flow > summary::-webkit-details-marker { display: none; }
details.flow .where {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 12.5px; word-break: break-all;
}
details.flow .body { padding: 4px 14px 14px; border-top: 1px solid var(--line); }
.pill {
  display: inline-block; font-size: 11.5px; font-weight: 650; padding: 3px 8px;
  border-radius: 999px; color: #fff; text-align: center; white-space: nowrap;
}
.pill.leak { background: var(--leak); }
.pill.unmasked { background: var(--unmasked); }
.pill.unknown { background: var(--unknown); }
.pill.ok { background: var(--ok); }

.stack {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 12px; background: #F7F9F8; border-radius: 6px; padding: 8px 10px;
  margin: 6px 0; white-space: pre-wrap; word-break: break-word;
}
.stack .hot { color: var(--token); font-weight: 700; }
dl.kv { display: grid; grid-template-columns: max-content 1fr; gap: 3px 14px; margin: 8px 0; }
dl.kv dt { font-weight: 650; font-size: 13px; }
dl.kv dd { margin: 0; font-size: 13px; }

table { border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 10px 0; }
th, td {
  text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line);
  vertical-align: top;
}
th { font-size: 12.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }

.appendix {
  border: 1px dashed var(--line); border-radius: 8px; padding: 16px 18px; background: #FAFBFB;
}
.limits { border-left: 3px solid var(--unmasked); padding: 4px 0 4px 14px; margin: 14px 0; }
footer.doc {
  margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--line);
  font-size: 12.5px; color: var(--muted);
}
footer.doc dl {
  display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 8px 0;
}
footer.doc dt { font-weight: 650; }
button#expand-all {
  font: inherit; font-size: 13px; background: none; border: 1px solid var(--line);
  border-radius: 6px; padding: 5px 10px; cursor: pointer; color: var(--muted);
}

@media print {
  .wrap { max-width: none; padding: 0 12mm; }
  h2 { break-before: auto; }
  details.flow { break-inside: avoid; }
  details.flow[open] > summary { pointer-events: none; }
  button#expand-all { display: none; }
  a { color: var(--ink); text-decoration: none; }
  .trust { border: 1px solid var(--accent); }
}
"""

#: The only script in the document, and the report is fully usable without
#: it -- every <details> can be opened by hand.
JS = """
(function () {
  var button = document.getElementById('expand-all');
  if (!button) return;
  button.addEventListener('click', function () {
    var open = button.getAttribute('data-open') !== 'true';
    document.querySelectorAll('details.flow').forEach(function (d) { d.open = open; });
    button.setAttribute('data-open', String(open));
    button.textContent = open ? 'Collapse all' : 'Expand all';
  });
})();
"""
