# maskflow-gateway

A drop-in **OpenAI / Anthropic-compatible proxy** that detects PII in a
request, replaces it with reversible typed placeholders before the request
reaches the provider, and restores the originals in the response —
**including mid-stream**.

Point your existing client's base URL at the gateway. No SDK change, no
code change.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",  # <- the gateway
    api_key="sk-...",  # <- your real OpenAI key, passed straight through
)
client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "Email Rahul at rahul.sharma@example.com about PAN ABCPE1234F"}
    ],
)
# OpenAI sees: "Email Rahul at <EMAIL_1> about PAN <PAN_1>"
# You get back: the model's reply with <EMAIL_1>/<PAN_1> restored to the real values
```

## Endpoints

| Route | What it does |
|---|---|
| `POST /v1/chat/completions` | OpenAI chat, streaming + non-streaming, tool calls |
| `POST /v1/messages` | Anthropic Messages, streaming + non-streaming, tool use |
| `POST /v1/embeddings` | masks each input **before** it is embedded — the RAG path |
| `POST /v1/mask` / `POST /v1/unmask` | direct masking, no upstream call |
| `GET /healthz` | liveness (never touches Redis) |
| `GET /readyz` | readiness — **503 fail-closed** if Redis `maxmemory-policy != noeviction` |
| `GET /metrics` | Prometheus |
| `GET /v1/entities` | every PII type the loaded packs detect |

## Streaming unmask

The model streams the reply in arbitrary chunks and a placeholder like
`<PERSON_NAME_1>` can be split across two SSE frames. The gateway parses
the provider's SSE, keeps a rolling buffer + a trie of the session's active
placeholders, and emits the longest prefix that is *certain* — a completed
placeholder (replaced) or a character that cannot begin any placeholder —
retaining only the tail that could still grow into one. A two-layer
decoder handles chunk splits mid-UTF-8. Property: for **any** chunking of a
masked reply, the concatenated stream equals the non-streaming
`unmask` result (fuzz-tested at every byte boundary).

## Sessions (multi-turn / tool loops)

Send `X-Maskflow-Session: <your opaque id>` to keep `<PHONE_1>` meaning the
same number across every turn and tool call of one agent run. Without the
header each request is masked and unmasked in isolation.

- `X-Maskflow-Session-TTL: <seconds>` overrides the default (3600), capped
  at `MASKFLOW_GATEWAY_SESSION_TTL_MAX_SECONDS` (86400).
- Keyed sessions need Redis (`MASKFLOW_GATEWAY_REDIS_URL`). Mappings are
  encrypted with **AES-256-GCM** (`MASKFLOW_GATEWAY_SESSION_KEY`, 32 random
  bytes hex) before they touch Redis, with a mandatory TTL.
- Redis **must** run `maxmemory-policy noeviction` — an evicted session
  mid-conversation means unmask finds nothing and a user sees raw
  `<PERSON_NAME_1>` text. `/readyz` returns 503 until this is fixed.

## Configuration

Every setting is an environment variable prefixed `MASKFLOW_GATEWAY_`:

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | must include the version segment |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com/v1` | |
| `UPSTREAM_API_KEY` | *(unset)* | set → gateway injects it; unset → client's own key is forwarded, nothing stored |
| `NER` | `0` | `1` enables the spaCy pass (bare Indian names & addresses); much slower — see `loadtest/` |
| `MIN_CONFIDENCE` | `0.5` | detection threshold |
| `REDIS_URL` | *(unset)* | unset → in-process ephemeral sessions only (single replica) |
| `SESSION_KEY` | *(unset)* | hex, 32 bytes; **required** when `REDIS_URL` is set |
| `SESSION_TTL_SECONDS` / `SESSION_TTL_MAX_SECONDS` | `3600` / `86400` | |
| `REQUIRE_MAXMEMORY_NOEVICTION` | `true` | |
| `MAX_REQUEST_BYTES` | `2000000` | |
| `UPSTREAM_TIMEOUT_SECONDS` / `UPSTREAM_CONNECT_TIMEOUT_SECONDS` | `120` / `10` | |
| `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_BURST` | `0` (off) | keyed by a hash of the client's `Authorization` |
| `TOOL_CALL_MAX_DEPTH` / `TOOL_CALL_MAX_ITEMS` | `32` / `10000` | bound the tool-argument JSON walk |
| `JSON_LOGS` | `1` | structured logs; every record also passes MaskFlow's PII scrub filter |
| `CORS_ALLOW_ORIGINS` | `[]` | JSON list |

The gateway's masking config comes only from these variables — it does not
read a `.maskflowrc`.

## Run

```bash
pip install "maskflow-gateway[redis]"
export MASKFLOW_GATEWAY_REDIS_URL=redis://localhost:6379/0
export MASKFLOW_GATEWAY_SESSION_KEY=$(python -c "import os;print(os.urandom(32).hex())")
maskflow-gateway --host 0.0.0.0 --port 8000 --workers 4
```

Deploy artifacts in [`deploy/`](deploy/): multi-arch `Dockerfile`,
`docker-compose.yml` (gateway + noeviction Redis), a Helm chart
(`deploy/helm/maskflow-gateway`, with HPA / PDB / ServiceMonitor), and
Fly / Render / Railway templates.

## Throughput

Published honestly, with the hardware, in [`loadtest/README.md`](loadtest/README.md).
Rough laptop floor: **~430 req/s** pattern-only, **~90 req/s** NER-enabled
(4 workers, Intel i7-9750H).

## License

MIT — like the rest of MaskFlow. No license gates, no paid flags, no
telemetry.
