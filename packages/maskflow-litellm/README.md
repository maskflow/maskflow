# maskflow-litellm

A [LiteLLM](https://github.com/BerriAI/litellm) **custom guardrail** that
masks PII on the way to the model provider and restores it in the reply.

It runs MaskFlow's detection engine, so alongside the usual PII (email,
phone, credit card, ...) it covers the **Indian identifiers** most PII
tools miss: Aadhaar, PAN, GSTIN, UPI VPA, IFSC, ABHA, Indian mobile / PIN
code / voter ID / passport / driving licence / vehicle registration, and
Indian names and addresses. That is the coverage the DPDP Act (in force
13 May 2027) actually asks for.

- **Reversible.** PII becomes a typed placeholder (`<AADHAAR_1>`), the
  provider never sees the real value, and the placeholder is swapped back
  before the response reaches your caller.
- **Streaming.** A placeholder split across SSE chunks is stitched back
  together, so the caller never sees a half-token.
- **Tool calls.** `tool_calls[].function.arguments` is walked as JSON
  (values only, keys untouched); inbound tool results are masked through
  the session so a value keeps the same token across a whole agent run.
- **Session-aware.** Same value → same token, stable for one request and,
  with a session id, across a multi-turn conversation.
- **MIT, no gates, no telemetry.**

## Install

```bash
pip install maskflow-litellm
# cross-turn sessions across proxy workers / replicas:
pip install "maskflow-litellm[redis]"
```

Runs wherever LiteLLM does (Python 3.11+; the current LiteLLM release does
not import on 3.10).

The first detection run downloads a small spaCy model for the name/address
recognizers. Set `maskflow_patterns_only: true` (below) to skip the NER
pass entirely if you only need the deterministic identifiers.

## Configure

In your LiteLLM `config.yaml`:

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

guardrails:
  - guardrail_name: maskflow
    litellm_params:
      guardrail: maskflow_litellm.MaskflowGuardrail
      mode: [pre_call, post_call]
      # all optional:
      maskflow_min_confidence: 0.5
      maskflow_patterns_only: false
      maskflow_session_ttl_seconds: 3600
      maskflow_redis_url: os.environ/MASKFLOW_REDIS_URL
      maskflow_session_encryption_key: os.environ/MASKFLOW_SESSION_KEY
```

`mode` **must include both `pre_call` and `post_call`.** `pre_call` masks
the request; `post_call` (and the streaming hook) restore the response.
With `pre_call` only, your caller sees `<AADHAAR_1>` tokens.

| `litellm_params` field | Default | Meaning |
|---|---|---|
| `maskflow_min_confidence` | `0.5` | Detection threshold. |
| `maskflow_patterns_only` | `false` | `true` skips the spaCy NER pass (faster; drops bare-name / address coverage). |
| `maskflow_session_ttl_seconds` | `3600` | Lifetime of a keyed session. |
| `maskflow_session_id_field` | `maskflow_session_id` | Request-`metadata` field the client uses to name a session. |
| `maskflow_redis_url` | – | Redis URL for cross-worker keyed sessions. Needs `[redis]` and the key below. |
| `maskflow_session_encryption_key` | – | base64 or hex AES-128/192/256 key; the session snapshot is AES-GCM encrypted before it touches Redis. |

## Use it

```bash
curl http://localhost:4000/v1/chat/completions \
  -H 'Authorization: Bearer sk-1234' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "My PAN is ABCDE1234F, file my return"}],
    "guardrails": ["maskflow"]
  }'
```

The provider receives `My PAN is <PAN_1>, file my return`; your caller gets
a reply with `ABCDE1234F` back in place.

### Multi-turn sessions

To keep `<PAN_1>` meaning the same value across requests, send a session
id, either as request metadata:

```json
{ "metadata": { "maskflow_session_id": "conv-42" }, "...": "..." }
```

or as a header: `X-Maskflow-Session: conv-42`.

Without an id, each request gets a fresh session (token identity is still
stable *within* the request, streaming and tool calls included).

On a single-worker proxy the in-process store handles keyed sessions. For
`--num_workers > 1` or multiple replicas, set `maskflow_redis_url` +
`maskflow_session_encryption_key`.

## PII safety

The guardrail never logs a mapping or an original value. The token→value
map lives in memory only (or AES-GCM encrypted in Redis); only an opaque
session ref is written to request metadata.

## Runnable example

`examples/config.yaml` is a complete proxy config; `examples/README.md` has
the `litellm --config …` command and curl calls that show masking,
streaming round-trip, and cross-turn sessions.

See `docs/litellm-guardrail.md` in the MaskFlow repo for the design notes
and the full request/response walk.
