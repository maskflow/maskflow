# DPDP Rule 6 mapping — Appendix A of the scan report

Every `maskflow scan` HTML report ends with **Appendix A — DPDP Rule 6
(Reasonable Security Safeguards) mapping**: a table relating each safeguard
in Rule 6 of the Digital Personal Data Protection Rules to what the scan and
MaskFlow contribute.

## This is a starting point, not legal advice

MaskFlow ships a **draft** mapping so the report is useful out of the box.
It reflects a plain reading of the published Rules; it is not a legal
opinion and does not account for your sector, your contracts, or the final
notified text. Review it with your Data Protection Officer or counsel
before relying on it.

## The draft mapping

| Rule 6 safeguard | How the scan / MaskFlow relates |
|---|---|
| Data security measures — encryption, obfuscation, masking, virtual tokens | MaskFlow's core purpose. `mask()` replaces detected PII with reversible typed tokens before a prompt leaves the process. This scan measures where that control was **not** yet in place. |
| Controlled access to computer resources | Out of MaskFlow's scope (it is a library). The findings show which downstream systems hold personal data and need access review. |
| Log visibility + detect / investigate / remediate unauthorised access | This scan **is** the detection step — it inventories personal data that reached third parties, from your own logs. Re-run on a schedule to monitor for regressions. |
| Continued processing / backups after a compromise | Out of scope. |
| Retention of logs enabling detection & investigation | The scan consumes exactly those logs; the report contains no raw values and is safe to retain as evidence of the review. |
| Contractual security terms with Data Processors | Out of scope. The provider / vendor list in the breakdown is the set of processors whose contracts should carry these terms. |

## Replacing it with your own text

The report has a stable marker where your authoritative mapping goes:

```html
<!-- DPDP_RULE6_APPENDIX -->
```

Post-process the generated HTML to substitute your block for that marker
(it sits just above the draft table, inside the appendix box). A one-liner:

```bash
maskflow scan ... -o report.html
python - <<'PY'
import pathlib
html = pathlib.Path("report.html").read_text()
mine = pathlib.Path("our-dpdp-appendix.html").read_text()
pathlib.Path("report.html").write_text(html.replace("<!-- DPDP_RULE6_APPENDIX -->", mine))
PY
```

The `--format json` output carries the same marker in `dpdp_appendix_slot`
if you render your own report from the structured data instead.
