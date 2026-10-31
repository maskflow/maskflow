# `maskflow/audit-action`

Find every place your codebase can send personal data to an LLM, and fail the
build when a new unmasked one appears.

```yaml
- uses: maskflow/maskflow/packaging/audit-action@main
  with:
    path: .
    ci: true          # fails on a new unmasked path (default)
```

The first run has no baseline, so the gate **skips** rather than failing —
create one and commit it:

```bash
pip install 'maskflow-cli[audit]'
maskflow audit --baseline
git add maskflow-audit.baseline.json
```

From then on a newly added unmasked call fails the job; a path that
disappears, or a new path that *is* masked, does not.

## Proving it, not guessing

```yaml
- uses: maskflow/maskflow/packaging/audit-action@main
  with:
    prove: true
    flows: "python -m pytest -q tests/integration"
```

With `prove: true` the action seeds synthetic Indian identities into your
test data, runs the command you name, and intercepts every provider-bound
request **before it leaves the runner** — returning a canned response so the
suite still passes. A canary observed in an outbound payload is reported as a
confirmed leak with the Python call stack captured at send time.

Nothing reaches a provider, no API key is needed, and no canary value is
written to disk or into the report.

## Outputs

| Output | |
|---|---|
| `total` | LLM egress paths found |
| `masked` | paths that are masked |
| `unmasked` | paths that are not |
| `confirmed-leaks` | paths a canary was observed escaping from |
| `report` | path to the generated report |

The HTML report is self-contained — inline CSS/JS, zero external requests —
so it can be downloaded from the artifact and emailed to an auditor.

Like [`scan-action`](../scan-action/), this is a candidate to be split into a
dedicated `maskflow/audit-action` repo for a Marketplace listing.
