# `maskflow/scan-action`

A GitHub Action that runs [`maskflow scan`](../../docs/scan.md) — reads
historical LLM traffic, produces a self-contained HTML report of what PII
reached third-party providers, uploads it as an artifact, and can fail the
job over a threshold. Everything runs on the runner; nothing is
transmitted.

> This action currently lives in-tree. Reference it by path:
> `maskflow/maskflow/packaging/scan-action@main`. It is a candidate to be
> split into a dedicated `maskflow/scan-action` repo for a Marketplace
> listing.

## Usage

```yaml
- uses: maskflow/maskflow/packaging/scan-action@main
  with:
    source: jsonl
    target: llm-requests.jsonl
    args: "--field 'messages[].content' --provider-field provider --deep"
    fail-over: "0"          # fail if ANY PII reached a provider
```

Scan an observability vendor on a schedule and just archive the report:

```yaml
on:
  schedule: [{ cron: "0 6 * * 1" }]   # Mondays 06:00 UTC
jobs:
  exposure:
    runs-on: ubuntu-latest
    steps:
      - uses: maskflow/maskflow/packaging/scan-action@main
        with:
          source: langfuse
          args: "--since ${{ github.event.repository.pushed_at }}"
        env:
          LANGFUSE_HOST: ${{ secrets.LANGFUSE_HOST }}
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
```

## Inputs

| input | default | notes |
|---|---|---|
| `source` | — (required) | `jsonl`/`ndjson`/`csv`/`dir`/`s3`/`postgres`/`langfuse`/`helicone`/`langsmith` |
| `target` | `""` | path / URI / connection string; omit for API sources |
| `args` | `""` | extra `maskflow scan` args as one string (quote `--field` selectors) |
| `format` | `html` | human report format (`html`/`json`/`csv`) |
| `output` | `maskflow-scan-report.html` | report path |
| `fail-over` | `""` | fail the job if total PII instances exceed this; empty never fails |
| `version` | latest | `maskflow-cli` version to install |
| `python-version` | `3.12` | runner Python |
| `upload-artifact` | `true` | upload the report + `maskflow-scan.json` |

## Outputs

| output | |
|---|---|
| `total` | total PII instances that reached providers |
| `distinct` | distinct PII values |
| `report` | path to the generated report |

## Notes

- The action always writes `maskflow-scan.json` (used for the threshold
  gate and uploaded alongside the report). If `format: html` it runs the
  scan twice — once for JSON, once for HTML.
- `s3` / `postgres` sources need `pip install 'maskflow-cli[s3]'` /
  `[postgres]`; set `version` accordingly or extend the install step.
- Credentials for the API sources come from the standard environment
  variables — pass them via `env:` as in the example above.
