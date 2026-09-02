"""Render a ScanSummary to one self-contained HTML file: inline CSS/JS, no
external requests, print-clean. Every dynamic string is HTML-escaped;
masked placeholders are then re-styled as tokens."""

from __future__ import annotations

import html
import re
from datetime import datetime

from .. import TRUST_LINE
from .assets import CSS, JS
from .summary import Breakdown, ScanSummary, SeverityRow, TimeBucket

# Bounded: matches an escaped "<TYPE_1>" / "<TYPE_1_a4f9>" placeholder only.
_TOKEN_RE = re.compile(r"&lt;[A-Z][A-Z_]{0,40}_\d{1,6}(?:_[0-9a-f]{1,8})?&gt;")


def render_html(summary: ScanSummary) -> str:
    s = summary
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>PII Exposure Scan — {esc(s.scope.source_kind)}</title>",
        f"<style>{CSS}</style>",
        "</head><body><div class='wrap'>",
        _header(s),
        _headline(s),
        _breakdowns(s),
        _severity(s),
        _appendix(s),
        _footer(s),
        "</div>",
        f"<script>{JS}</script>",
        "</body></html>",
    ]
    return "\n".join(parts)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _tokenize(text: str) -> str:
    escaped = esc(text)
    return _TOKEN_RE.sub(lambda m: f'<span class="token">{m.group(0)}</span>', escaped)


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M %Z").strip()


def _header(s: ScanSummary) -> str:
    scope = s.scope
    when = _fmt_dt(scope.generated_at)
    rng = ""
    if scope.date_range:
        lo, hi = scope.date_range
        rng = f" · traffic {lo.date().isoformat()} to {hi.date().isoformat()}"
    return f"""
<header class="doc">
  <div class="brand"><span class="name">MaskFlow</span>
    <span class="muted small">PII Exposure Scan</span></div>
  <h1>What PII already reached third-party LLM providers</h1>
  <p class="muted small">Generated {esc(when)}{esc(rng)}</p>
  <div class="trust">{esc(TRUST_LINE)}</div>
  <p class="scope small muted">
    Source: <span class="mono">{esc(scope.source_kind)}</span>
    (<span class="mono">{esc(scope.source_target)}</span>) ·
    {scope.records_processed:,} records examined ·
    {scope.records_with_pii:,} contained PII ·
    detection: {esc(scope.detection_mode)}
  </p>
</header>"""


def _headline(s: ScanSummary) -> str:
    est = '<span class="est-flag">includes estimate</span>' if s.headline_has_estimate else ""
    providers = ", ".join(esc(p) for p in s.providers) or "unattributed provider(s)"
    rng = ""
    if s.scope.date_range:
        lo, hi = s.scope.date_range
        rng = f" between {lo.date().isoformat()} and {hi.date().isoformat()}"
    caption = (
        f"{s.headline_total:,} PII instances — across {s.headline_distinct:,} distinct "
        f"values — were sent to {providers}{esc(rng)}."
    )
    note = ""
    if s.headline_has_estimate:
        note = (
            f'<p class="small muted">Names and addresses were measured on '
            f"{s.scope.ner_sample_records:,} sampled records and scaled by "
            f"×{s.scope.extrapolation_factor:.1f}. Run <span class='mono'>--deep</span> "
            f"for exact figures.</p>"
        )
    return f"""
<section class="headline">
  <div class="n">{s.headline_total:,}{est}</div>
  <p class="cap">{caption}</p>
  {note}
</section>"""


def _bar_chart(rows: list[Breakdown]) -> str:
    if not rows:
        return '<p class="small muted">No data.</p>'
    top = max((r.count for r in rows), default=1) or 1
    out = ['<div class="chart">']
    for r in rows:
        pct = 100.0 * r.count / top
        flag = ' <span class="est-flag">est</span>' if r.estimated else ""
        distinct = f" · {r.distinct:,} distinct" if r.distinct is not None else ""
        fill = f'<span class="bar-fill" style="width:{pct:.1f}%"></span>'
        out.append(
            f'<div class="bar-row"><span class="label" title="{esc(r.label)}">'
            f"{esc(r.label)}{flag}</span>"
            f'<span class="bar-track">{fill}</span>'
            f'<span class="val">{r.count:,}{esc(distinct)}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def _spark(buckets: list[TimeBucket], unit: str) -> str:
    if not buckets:
        return '<p class="small muted">No timestamps available in this source.</p>'
    n = len(buckets)
    top = max((b.count for b in buckets), default=1) or 1
    w, h = 840, 120
    bw = w / n
    bars = []
    for i, b in enumerate(buckets):
        bh = (h - 18) * b.count / top
        x = i * bw
        bars.append(
            f'<rect x="{x:.1f}" y="{h - 18 - bh:.1f}" width="{max(bw - 1.5, 1):.1f}" '
            f'height="{bh:.1f}"><title>{esc(b.start)}: {b.count:,}</title></rect>'
        )
    labels = (
        f'<text x="0" y="{h - 4}" font-size="10" fill="#5B6763">{esc(buckets[0].start)}</text>'
        f'<text x="{w}" y="{h - 4}" font-size="10" fill="#5B6763" '
        f'text-anchor="end">{esc(buckets[-1].start)}</text>'
    )
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
        f'role="img" aria-label="PII instances per {unit}">'
        f'<line class="axis" x1="0" y1="{h - 18}" x2="{w}" y2="{h - 18}"/>'
        f"{''.join(bars)}{labels}</svg>"
    )


def _breakdowns(s: ScanSummary) -> str:
    return f"""
<h2>Breakdowns</h2>
<h3>By entity type</h3>
{_bar_chart(list(s.by_entity_type))}
<h3>By provider</h3>
{_bar_chart(list(s.by_provider))}
<h3>By service / model</h3>
{_bar_chart(list(s.by_service))}
<h3>Over time (per {esc(s.time_bucket_unit)})</h3>
{_spark(list(s.time_series), s.time_bucket_unit)}"""


def _severity(s: ScanSummary) -> str:
    rows = "".join(_sev_row(r) for r in s.severity_rows)
    return f"""
<h2>Severity ranking
  <button id="expand-all" type="button" class="small"
    style="float:right;font:inherit;font-size:12px;border:1px solid var(--line);
    background:#fff;border-radius:6px;padding:3px 9px;cursor:pointer">Expand all</button>
</h2>
<p class="small muted">Ordered most to least severe. Severity reflects what the
class of value enables if misused, not detector confidence.</p>
{rows or '<p class="muted">No PII detected.</p>'}"""


def _sev_row(r: SeverityRow) -> str:
    est = ' <span class="est-flag">est</span>' if r.estimated else ""
    distinct = f"{r.distinct:,}{'+' if r.distinct_is_lower_bound else ''}"
    providers = ", ".join(esc(p) for p in r.providers) or "—"
    excerpts = "".join(f'<div class="excerpt">{_tokenize(x)}</div>' for x in r.excerpts)
    if not excerpts:
        excerpts = '<p class="small muted">No example context retained for this type.</p>'
    return f"""
<details class="sev">
  <summary>
    <span class="pill {esc(r.severity)}">{esc(r.severity)}</span>
    <span><strong>{esc(r.entity_type)}</strong>{est}
      <span class="why">— {esc(r.why_it_matters)}</span></span>
    <span class="small muted">{r.count:,} instances</span>
  </summary>
  <div class="body">
    <p class="small muted">{r.count:,} instances · {esc(distinct)} distinct values ·
      providers: {providers}</p>
    <p class="small muted">Masked example contexts (raw values never shown):</p>
    {excerpts}
  </div>
</details>"""


def _appendix(s: ScanSummary) -> str:
    return f"""
<h2>Appendix A — DPDP Rule 6 (Reasonable Security Safeguards) mapping</h2>
<div class="appendix">
  <p class="small muted">This section maps the findings above to the safeguards
  expected under Rule 6 of the Digital Personal Data Protection Rules. The
  mapping text is maintained by MaskFlow and inserted here.</p>
  {s.dpdp_appendix_slot}
  <table>
    <thead><tr><th>Rule 6 safeguard</th><th>How this scan / MaskFlow addresses it</th></tr></thead>
    <tbody>
      <tr><td>Encryption, masking or equivalent controls for personal data</td>
          <td class="muted">Provided by MaskFlow — pending</td></tr>
      <tr><td>Controls on access to personal data</td>
          <td class="muted">Provided by MaskFlow — pending</td></tr>
      <tr><td>Logging, monitoring and review to detect unauthorised processing</td>
          <td class="muted">Provided by MaskFlow — pending</td></tr>
      <tr><td>Measures to enable continued processing after a breach</td>
          <td class="muted">Provided by MaskFlow — pending</td></tr>
    </tbody>
  </table>
</div>"""


def _footer(s: ScanSummary) -> str:
    m = s.methodology
    versions = "".join(
        f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in sorted(m.detector_versions.items())
    )
    entities = ", ".join(esc(e) for e in m.entity_types_scanned) or "—"
    return f"""
<footer class="doc">
  <h3 style="color:var(--muted)">Methodology</h3>
  <dl>{versions}</dl>
  <p>Entity types considered: {entities}</p>
  <p>{esc(m.thresholds_note)}</p>
  <p>{esc(m.not_scanned_note)}</p>
  <p>Corpus fingerprint: <span class="mono">{esc(m.corpus_fingerprint)}</span></p>
  <p><strong>No raw PII value appears anywhere in this document.</strong>
     All identifiers are shown as typed placeholders such as
     <span class="token">&lt;AADHAAR_1&gt;</span>.</p>
  <p class="muted">{esc(TRUST_LINE)}</p>
</footer>"""
