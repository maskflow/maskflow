# maskflow-evidence

A **metadata-only, verifiable record of what MaskFlow masked** — never the
values themselves. Publishing the schema and shipping the emitters in the
open lets any user confirm, by reading the code, exactly what leaves their
environment.

> Part of [MaskFlow](https://github.com/maskflow/maskflow). MIT, free
> forever, no telemetry.

## What an event looks like

```json
{"event_id":"…","ts":"2026-09-07T12:00:00Z","session_id":"…","service":"support-bot",
 "environment":"prod","entity_type":"AADHAAR","count":1,"score":0.98,
 "recognizer":"pattern:AADHAAR","action":"masked","provider":"openai","model":"gpt-4o",
 "pack_version":"0.5.0","engine_version":"0.6.0"}
```

There is **no field that can carry free text.** Every string is a bounded
slug; there is no place for a detected value, a placeholder, or the mapping
between them. This is enforced structurally in `schema.py` and in CI by
`tests/test_schema_metadata_only.py`.

## Off by default

Nothing is emitted unless you turn it on. In `.maskflowrc`:

```toml
[evidence]
enabled     = true
sink        = "file"          # stdout | file | syslog | webhook | otlp
path        = "evidence.log"
service     = "support-bot"
environment = "prod"
```

The gateway reads `MASKFLOW_GATEWAY_EVIDENCE_*` environment variables with
the same names.

## Sinks

| sink | transport | extra |
|---|---|---|
| `stdout` | one JSON line per event | — |
| `file` | size-rotated JSON lines | — |
| `syslog` | `SysLogHandler` | — |
| `webhook` | `POST` JSON per event | `maskflow-evidence[webhook]` |
| `otlp` | OpenTelemetry log records | `maskflow-evidence[otlp]` |

## What is deliberately **not** collected

Raw values, masked values, the mapping, request/response bodies, prompt
text, and any user identifier beyond a caller-supplied opaque `session_id`.
See `docs/evidence.md` for the full statement.
