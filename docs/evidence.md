# Evidence — a metadata-only record of what was masked

`maskflow-evidence` produces an **open, verifiable record of *what* MaskFlow
masked** — an entity type, a count, the recognizer that fired, the action
taken, and the context it happened in. It never contains the detected
value, the placeholder it became, or the mapping between them.

Publishing the schema and shipping the emitters in the open-source library
is what lets any user confirm, *by reading the code*, exactly what leaves
their environment.

> **Status.** The event schema and emitters (issue
> [#41](https://github.com/maskflow/maskflow/issues/41)) are shipped. The
> mapping from these events to specific DPDP / ISO 27001 controls, the
> recommended retention period, and signed accuracy attestations (issues
> [#42](https://github.com/maskflow/maskflow/issues/42),
> [#43](https://github.com/maskflow/maskflow/issues/43)) are still being
> validated with compliance practitioners and are **not** part of this
> release. See "Compliance mapping" below.

## The event schema

One event per `(entity_type, recognizer, action)` per masking call:

| field | type | meaning |
|---|---|---|
| `event_id` | uuid4 hex | unique per event |
| `ts` | RFC3339 UTC | when the event was produced |
| `session_id` | opaque slug | a hash or uuid supplied by the caller — never a username or email |
| `service` | slug | your application name (from config) |
| `environment` | slug | `prod` / `staging` / … (from config) |
| `entity_type` | slug | e.g. `AADHAAR`, `PAN`, `EMAIL` |
| `count` | int ≥ 1 | how many spans of this type/recognizer in the call |
| `score` | float 0–1 | the **lowest** confidence in the group (the most conservative claim) |
| `recognizer` | slug | e.g. `pattern:AADHAAR`, `ner:PERSON` |
| `action` | enum | `masked` \| `redacted` \| `surrogate` \| `passed` |
| `provider` | slug \| null | the LLM provider, when known |
| `model` | slug \| null | the model, when known |
| `pack_version` | version | the recognizer pack that did the detection |
| `engine_version` | version | `maskflow-core` version |

**No field can carry free text.** Every string is a bounded slug; there is
no place for a value to appear. This is enforced structurally in
`schema.py` and in CI by `test_schema_metadata_only.py` (a static field-set
audit, a property test over arbitrary input, and an AST check that the
derivation code never reads a detected value). The CI suite also runs
events emitted from a PII corpus through `maskflow-core`'s pattern/checksum
detectors (`guard.assert_no_pii`) and asserts nothing is found.

## What is deliberately **not** collected

- the detected values, in any form
- the masked placeholders or surrogate values
- the token → value mapping
- request or response bodies, prompts, or completions
- any user identifier beyond the caller-supplied opaque `session_id`
- IP addresses, headers, or auth credentials

## Turning it on

Off by default. In your `.maskflowrc`:

```toml
[evidence]
enabled     = true
sink        = "file"          # stdout | file | syslog | webhook | otlp
path        = "evidence.log"  # file sink
max_bytes   = 10_000_000
backups     = 5
service     = "support-bot"
environment = "prod"
# url     = "https://collector.internal/evidence"   # webhook / otlp
```

### CLI

```bash
maskflow explain --evidence-file evidence.log "Aadhaar 2345 6789 0124, PAN ABCPE1234F"
```

`--evidence` alone uses the `[evidence]` section; `--evidence-file PATH`
forces a file sink at `PATH`.

### Gateway

The gateway reads the same `.maskflowrc` `[evidence]` section, and
`MASKFLOW_GATEWAY_EVIDENCE_*` environment variables override it
(`MASKFLOW_GATEWAY_EVIDENCE_ENABLED`, `_SINK`, `_PATH`, `_SERVICE`,
`_ENVIRONMENT`, `_URL`, …). Every proxied request then emits one event per
detected type. The client's `X-Maskflow-Session` header, if any, is
**hashed** into `session_id` — never emitted raw. A Prometheus counter
`maskflow_evidence_emitted_total{sink}` tracks volume.

## Sinks

| sink | transport | extra |
|---|---|---|
| `stdout` | one JSON line per event on stdout | — |
| `file` | size-rotated JSON-lines file | — |
| `syslog` | `SysLogHandler` (local socket or `host:port`) | — |
| `webhook` | `POST` one JSON object per event | `maskflow-evidence[webhook]` |
| `otlp` | OpenTelemetry log records | `maskflow-evidence[otlp]` |

An emit failure is logged and the event dropped — evidence never breaks a
masking call.

## Grafana

`contrib/grafana-dashboard.json` (in the `maskflow-evidence` package) is a
starter dashboard over the gateway's Prometheus metrics: evidence emission
rate by sink, detections by entity type, and mask-stage latency. Import it
and pick your Prometheus datasource. It has **panels only** — no
"compliance controls covered" framing until issue #42 lands.

## Compliance mapping — pending #42

Which artifact an auditor actually accepts, how these events map to DPDP
Rule 6 / ISO 27001 controls, and the expected retention period are being
validated with data-protection officers, security leads, and compliance
consultants before anything is asserted here. This section will be filled
in from those findings. Until then, treat the events as raw material for
your own control narrative, reviewed with your DPO or counsel — the same
caveat as [the DPDP Rule 6 mapping](dpdp-rule6.md).
