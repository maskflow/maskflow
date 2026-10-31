"""AuditSummary -> one self-contained HTML file.

f-strings only -- no Jinja, no template files, no external assets -- same
construction and the same reason as maskflow-cli's scan report: the
document must be provably self-contained, so there is nothing to fetch at
render time and nothing to path-resolve at read time.

Every dynamic value goes through `esc()`. The only strings interpolated raw
are the author-written constants in this module (the Rule 6 rows, which
carry their own markup).

Like every renderer here, this reads an `AuditSummary` and nothing else, so
"does this report leak?" is answerable by inspecting that one object.
"""

from __future__ import annotations

import html as html_module

from .assets import CSS, JS
from .summary import AuditSummary, Breakdown, FlowRow

#: Printed in the report and by the CLI. The audit makes no network request
#: at all -- it parses source and intercepts the project's own traffic
#: before it leaves the process.
TRUST_LINE = "Runs entirely locally. Nothing is transmitted."

_STATUS_LABEL: dict[str, tuple[str, str]] = {
    "unmasked": ("UNMASKED", "unmasked"),
    "unknown": ("UNKNOWN", "unknown"),
    "masked_via_mask_call": ("masked: mask()", "ok"),
    "masked_via_gateway_base_url": ("masked: gateway", "ok"),
    "masked_via_integration": ("masked: integration", "ok"),
}

_CANARY_LABEL: dict[str, str] = {
    "escaped": "canary ESCAPED",
    "contained": "canary contained",
    "not_exercised": "not exercised by the run",
    "not_run": "canaries not run",
}


def esc(value: object) -> str:
    return html_module.escape(str(value), quote=True)


def _bar_chart(rows: tuple[Breakdown, ...]) -> str:
    if not rows:
        return '<p class="small muted">Nothing to show.</p>'
    largest = max(r.count for r in rows) or 1
    bars = "".join(
        f'<div class="bar"><div class="label">{esc(r.label)}</div>'
        f'<div class="track"><div class="fill" style="width:{pct}%"></div></div>'
        f'<div class="n">{r.count:,}</div></div>'
        for r, pct in ((row, 100 * row.count // largest) for row in rows)
    )
    return f'<div class="bars">{bars}</div>'


def _header(s: AuditSummary) -> str:
    scope = s.scope
    return f"""
<div class="brand">MaskFlow &middot; LLM egress audit</div>
<h1>Where can personal data reach an LLM?</h1>
<p class="scope">Generated {esc(scope.generated_at.isoformat())} &middot;
  {scope.files_examined:,} Python file(s) examined
  {f"&middot; {scope.files_skipped} skipped" if scope.files_skipped else ""}</p>
<div class="trust"><strong>{esc(TRUST_LINE)}</strong> Your source was parsed, never
  executed. No request left this machine &mdash; the canary run intercepts the
  application's own outbound traffic before it reaches a provider.</div>
<p class="scope mono">{esc(scope.root)}</p>"""


def _headline(s: AuditSummary) -> str:
    coverage = s.coverage
    flags = ""
    if coverage.confirmed_leaks:
        flags += f'<span class="flag">{coverage.confirmed_leaks} confirmed leak(s)</span>'
    if coverage.unmasked:
        flags += f'<span class="flag warn">{coverage.unmasked} unmasked</span>'
    if coverage.unknown:
        flags += f'<span class="flag info">{coverage.unknown} unknown</span>'

    if not s.scope.canaries_run:
        caveat = (
            "Canaries were not run, so every finding below is <strong>predicted</strong> "
            "from static analysis, not proven. Re-run with <span class='mono'>--prove</span> "
            "to confirm which paths actually leak."
        )
    elif coverage.confirmed_leaks:
        caveat = (
            "A <strong>confirmed</strong> leak means a synthetic identity was observed "
            "reaching a provider from that line, with the call stack captured at send time."
        )
    else:
        caveat = (
            "The canary run observed no identifier escaping. Paths marked "
            "<em>not exercised</em> were never reached by the run and remain unproven."
        )

    return f"""
<div class="headline">
  <div class="n">{coverage.masked}<span class="muted" style="font-size:28px">
    /{coverage.total_flows}</span></div>
  <div class="cap">{esc(s.headline)}{flags}</div>
</div>
<p class="small muted">{caveat}</p>"""


def _flow_block(flow: FlowRow) -> str:
    label, pill = _STATUS_LABEL.get(flow.masking_status, (flow.masking_status, "unknown"))
    is_leak = flow.canary_status == "escaped"
    if is_leak:
        label, pill = "LEAK PROVEN", "leak"

    sources = (
        ", ".join(
            f"{esc(src.kind)}{':' + esc(src.detail) if src.detail else ''}" for src in flow.sources
        )
        or "<em>not traced</em>"
    )

    escapes = ""
    if flow.canary_escapes:
        rows = "".join(
            f"<tr><td class='mono'>{esc(e.entity_type)}</td><td>{esc(e.form)}</td>"
            f"<td class='mono'>{esc(e.host)}{esc(e.path)}</td><td>{esc(e.library)}</td></tr>"
            for e in flow.canary_escapes
        )
        stacks = ""
        for escape in flow.canary_escapes[:1]:
            frames = "\n".join(
                f"<span class='hot'>{esc(f)}</span>" if i == len(escape.app_stack) - 1 else esc(f)
                for i, f in enumerate(escape.app_stack)
            )
            stacks = f"<h3>Call stack at send time</h3><div class='stack'>{frames}</div>"
        escapes = f"""
<h3>Observed canary escapes</h3>
<table><thead><tr><th>Entity</th><th>Found as</th><th>Destination</th><th>Via</th></tr></thead>
<tbody>{rows}</tbody></table>
{stacks}"""

    explanation = "".join(f"<li>{esc(step)}</li>" for step in flow.explanation)

    return f"""
<details class="flow{" leak" if is_leak else ""}"{" open" if is_leak else ""}>
  <summary>
    <span class="pill {pill}">{esc(label)}</span>
    <span class="where">{esc(flow.file)}:{flow.line}</span>
    <span class="small muted">{esc(flow.provider)}</span>
  </summary>
  <div class="body">
    <dl class="kv">
      <dt>Flow</dt><dd class="mono">{esc(flow.flow_id)}</dd>
      <dt>Sink</dt><dd>{esc(flow.sink_id)} ({esc(flow.category)})</dd>
      <dt>Destination</dt><dd class="mono">{esc(flow.host) or "&mdash;"}</dd>
      <dt>Call</dt><dd class="mono">{esc(flow.call_path)}</dd>
      <dt>Function</dt><dd class="mono">{esc(flow.function) or "&lt;module&gt;"}</dd>
      <dt>Payload</dt><dd class="mono">{esc(", ".join(flow.payload_args)) or "&mdash;"}</dd>
      <dt>Sources</dt><dd>{sources}</dd>
      <dt>Confidence</dt><dd>{esc(flow.confidence)}</dd>
      <dt>Canary</dt><dd>{esc(_CANARY_LABEL.get(flow.canary_status, flow.canary_status))}</dd>
    </dl>
    <p class="small">{esc(flow.masking_reason)}</p>
    {
        f"<h3>How this was decided</h3><ul class='small muted'>{explanation}</ul>"
        if explanation
        else ""
    }
    {escapes}
  </div>
</details>"""


def _flows(s: AuditSummary) -> str:
    if not s.flows:
        return """
<h2>Flows</h2>
<p>No LLM egress paths were found. <strong>That means none of the sinks in the
registry appear in this tree &mdash; not that none exist.</strong> See the limits
below before treating this as a clean bill of health.</p>"""
    return f"""
<h2>Flows <button id="expand-all" data-open="false">Expand all</button></h2>
<p class="small muted">Confirmed leaks first, then unmasked, then everything else.</p>
{"".join(_flow_block(f) for f in s.flows)}"""


def _breakdowns(s: AuditSummary) -> str:
    return f"""
<h2>Breakdown</h2>
<h3>By masking status</h3>
{_bar_chart(s.by_status)}
<h3>By provider</h3>
{_bar_chart(s.by_provider)}
<h3>By sink category</h3>
{_bar_chart(s.by_category)}"""


def _overrides_block(warnings: str) -> str:
    if not warnings:
        return ""
    return (
        "<p class='small'><strong>Overrides in effect:</strong></p>"
        f"<ul class='small'>{warnings}</ul>"
    )


def _unattributed_block(count: int) -> str:
    """An escape with no matching flow means discovery missed a sink.

    Said plainly, and asked for: a canary that got out through a path
    static analysis never found is the most useful bug report this tool
    can produce about itself.
    """
    if not count:
        return ""
    return (
        f"<p class='small'><strong>{count} escape(s) could not be matched to a "
        "discovered flow.</strong> That means discovery missed a sink: the canary "
        "got out through a path static analysis did not find. Please report it "
        "&mdash; it is the most useful bug report this tool can produce about "
        "itself.</p>"
    )


def _canary_section(s: AuditSummary) -> str:
    run = s.canary_run
    if run is None:
        return """
<h2>Canary run</h2>
<p>Not run. Every finding in this report is predicted from static analysis.
Re-run with <span class="mono">--prove</span> to seed synthetic identities,
intercept the application's outbound requests, and confirm which paths
actually leak.</p>"""

    warnings = "".join(f"<li>{esc(w)}</li>" for w in run.warnings) if run.warnings else ""
    return f"""
<h2>Canary run</h2>
<dl class="kv">
  <dt>Command</dt><dd class="mono">{esc(" ".join(run.command))}</dd>
  <dt>Exit code</dt><dd>{run.command_exit_code}</dd>
  <dt>Seed</dt><dd class="mono">{run.seed}</dd>
  <dt>Identities</dt><dd>{run.identities}</dd>
  <dt>Entity types</dt><dd class="small">{esc(", ".join(run.entity_types))}</dd>
  <dt>Seeded into</dt><dd class="small mono">{esc(", ".join(run.seeded_targets)) or "&mdash;"}</dd>
  <dt>Requests intercepted</dt><dd>{run.requests_intercepted}</dd>
  <dt>Escapes observed</dt><dd>{run.escapes_observed}</dd>
  <dt>Unattributed</dt><dd>{run.unattributed_escapes}</dd>
</dl>
<p class="small muted">Every seeded value is synthetic, generated from the seed
above and re-validated against MaskFlow's own validators before use. No value
appears in this report. Canary values never left this machine: the audit
intercepts the request and returns a canned response, so nothing reached a
provider.</p>
{_overrides_block(warnings)}
{f"<p class='small'>{esc(run.note)}</p>" if run.note else ""}
{_unattributed_block(run.unattributed_escapes)}"""


# Draft mapping of DPDP Rules, Rule 6 ("Reasonable security safeguards") to
# what this audit and MaskFlow contribute. Written by MaskFlow as a starting
# point for your DPO -- it is not legal advice and the report says so. A
# deployment can replace the whole block by substituting its own HTML for the
# `<!-- DPDP_RULE6_APPENDIX -->` marker (see docs/dpdp-rule6.md). The clause
# column is deliberately identical to the scan report's, so the two documents
# read as one body of evidence.
_DPDP_RULE6_ROWS = (
    (
        "Data security measures such as encryption, obfuscation, masking or "
        "the use of virtual tokens",
        "This audit measures exactly that control, at the point it has to hold: "
        "every code path by which personal data can reach an LLM provider, and "
        "whether <code>mask()</code>, the MaskFlow gateway, or a framework "
        "integration is actually in that path. A confirmed leak is a measured "
        "failure of this safeguard, with the call stack attached.",
    ),
    (
        "Appropriate measures to control access to computer resources used by "
        "the Data Fiduciary or a Data Processor",
        "Out of MaskFlow's scope &mdash; it is a library, not an access-control "
        "system. The provider and host list above is the set of external systems "
        "this codebase can send personal data to, and therefore the set whose "
        "access needs review.",
    ),
    (
        "Visibility on access to personal data through logs and monitoring, "
        "and the ability to detect, investigate and remediate unauthorised "
        "access",
        "This audit is the <em>pre-incident</em> half of that: it inventories the "
        "paths before data moves, rather than reading logs afterwards. Run it in "
        "CI (<span class='mono'>--ci</span>) and a newly added unmasked path fails "
        "the build, which is the remediation loop made automatic.",
    ),
    (
        "Reasonable measures for continued processing (including backups) in "
        "the event of a compromise",
        "Out of MaskFlow's scope.",
    ),
    (
        "Retention of logs and personal data for a period enabling detection "
        "and investigation of unauthorised access",
        "This report contains no personal data and no canary value &mdash; only "
        "file paths, call paths, column names and counts &mdash; so it is safe to "
        "retain and to share as evidence that the review happened, and dated "
        "proof of which paths were masked on the day it ran.",
    ),
    (
        "Contractual terms with Data Processors requiring reasonable security safeguards",
        "Out of MaskFlow's scope. The provider list above is the set of processors "
        "whose contracts should carry these terms &mdash; including the "
        "observability vendors, which an audit of model calls alone would miss.",
    ),
)


def _appendix(s: AuditSummary) -> str:
    rows = "".join(f"<tr><td>{clause}</td><td>{how}</td></tr>" for clause, how in _DPDP_RULE6_ROWS)
    return f"""
<h2>Appendix A &mdash; DPDP Rule 6 (Reasonable Security Safeguards) mapping</h2>
<div class="appendix">
  <p class="small muted">A starting-point mapping of Rule 6 of the Digital Personal
  Data Protection Rules to what this audit and MaskFlow contribute. Written by
  MaskFlow, <strong>not legal advice</strong> &mdash; review it against your Data
  Protection Officer's reading. A deployment can replace this block by
  substituting its own text for the
  <span class="mono">&lt;!-- DPDP_RULE6_APPENDIX --&gt;</span> marker.</p>
  {s.dpdp_appendix_slot}
  <table>
    <thead><tr><th>Rule 6 safeguard</th><th>How this audit / MaskFlow relates</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def _limits(s: AuditSummary) -> str:
    method = s.methodology
    skipped = ""
    if s.skipped_files:
        items = "".join(
            f"<li class='mono'>{esc(f.file)} &mdash; {esc(f.reason)}</li>"
            for f in s.skipped_files[:20]
        )
        more = (
            f"<li class='muted'>and {len(s.skipped_files) - 20} more</li>"
            if len(s.skipped_files) > 20
            else ""
        )
        skipped = f"<h3>Files not examined</h3><ul class='small'>{items}{more}</ul>"
    return f"""
<h2>What this audit did not do</h2>
<div class="limits">
  <p class="small">{esc(method.limits_note)}</p>
  <p class="small">{esc(method.not_detected_note)}</p>
</div>
{skipped}"""


def _footer(s: AuditSummary) -> str:
    method = s.methodology
    versions = "".join(
        f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in sorted(method.detector_versions.items())
    )
    return f"""
<footer class="doc">
  <p><strong>Methodology.</strong> Static discovery over Python with the standard
  library's <span class="mono">ast</span> module, against a registry of
  {method.sinks_known} known egress sinks (registry v{method.registry_version}).</p>
  <dl>{versions}
    <dt>schema</dt><dd>{esc(s.schema_version)}</dd>
    <dt>config fingerprint</dt><dd class="mono">{esc(method.config_fingerprint)}</dd>
  </dl>
  <p>No raw PII value, no canary value, and no line of the audited source
  appears anywhere in this document.</p>
</footer>"""


def render_html(summary: AuditSummary) -> str:
    s = summary
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>LLM Egress Audit &mdash; {esc(s.coverage.total_flows)} path(s)</title>",
        f"<style>{CSS}</style>",
        "</head><body><div class='wrap'>",
        _header(s),
        _headline(s),
        _flows(s),
        _breakdowns(s),
        _canary_section(s),
        _appendix(s),
        _limits(s),
        _footer(s),
        "</div>",
        f"<script>{JS}</script>",
        "</body></html>",
    ]
    return "\n".join(parts)
