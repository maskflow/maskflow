# MaskFlow Gateway

`packages/maskflow-gateway` is an OpenAI/Anthropic-compatible reverse proxy.
It masks PII on the way to the provider and restores it on the way back,
with correct behaviour for streamed responses and tool calls. It reuses the
same detection engine and session identity model as `maskflow-sdk` — the
gateway is the SDK's `Session` behind an HTTP server, plus a streaming
unmasker.

See `packages/maskflow-gateway/README.md` for the endpoint list and the
full environment-variable reference. This document covers the parts worth
understanding before you run it in production.

## Request flow

Identical for streaming and non-streaming, so an error always produces a
real HTTP status before any response byte is committed:

1. size-limit + JSON-parse the body
2. per-key rate limit (token bucket, keyed by a hash of `Authorization`)
3. open the session — restore its mapping from Redis if the client sent
   `X-Maskflow-Session`
4. **mask the request** — walk message content, multimodal text parts,
   `tool_calls[].function.arguments` (a JSON walk: string/number *values*
   only, never keys), Anthropic `system` blocks, `tool_use` inputs, and
   inbound `tool_result` / `role:"tool"` content
5. **persist the session snapshot** — before the upstream call, so a crash
   mid-stream never loses the mapping needed to unmask
6. call the upstream with the client's own credential (unless
   `MASKFLOW_GATEWAY_UPSTREAM_API_KEY` is configured), peeking the status
   before committing to a streaming response
7. **restore the response** — a structural walk for JSON, the incremental
   unmasker for SSE
8. record metrics, close the session

Inbound tool results are **masked** through the session, not unmasked —
the model never sees a raw value. Masking through the *session* means a
value already seen keeps its existing placeholder, and a new value gets the
next counter.

## Streaming unmask

### The problem

The model streams the masked reply in arbitrary chunks. A placeholder
(`<PERSON_NAME_1>`) can be split across two chunks, and — because the reply
text lives inside JSON inside SSE frames — the two halves can have
`"}}]}\n\ndata: {` between them on the wire. We cannot forward a partial
placeholder (the client would render `<PERSON_NA` then the real name
later), and we will not buffer the whole reply.

### The algorithm

The gateway parses the provider's SSE, reconstructs the logical assistant
message, and runs `StreamingUnmasker` on the **clean concatenated content
text** (no JSON, no SSE), then re-frames provider-native chunks with
correctly JSON-encoded content.

`StreamingUnmasker` holds a rolling buffer and a character trie of the
session's active placeholders. On each `feed(chunk)`:

```
buffer += chunk
i = 0
while i < len(buffer):
    classify buffer at i by walking the trie:
      MATCH  -> a complete placeholder starts here: emit its original,
                advance past it (the original is committed, never re-scanned)
      PREFIX -> ran out of buffer still on a live trie path: stop,
                retain buffer[i:] for the next chunk
      NONE   -> this character cannot begin any placeholder: emit it,
                advance one
buffer = buffer[i:]   # always "" or a proper prefix of some placeholder
```

`flush()` at end-of-stream releases whatever is left verbatim — a retained
prefix can never complete.

This is correct for any chunking because the loop only emits a decision
when it is **already certain**: a completed placeholder (nothing extends
one — every placeholder ends in `>`, which appears nowhere else) or a
character on a dead trie path. Every position whose decision could still
change is the `PREFIX` case, which is retained.

### Two layers

- **byte layer** (`ByteStreamingUnmasker`): an incremental UTF-8 decoder
  holds an incomplete trailing multi-byte sequence, so a chunk split
  mid-code-point is handled before the trie ever sees it. Placeholders are
  ASCII; originals may be any Unicode but are only ever emitted.
- **char layer** (`StreamingUnmasker`): the trie + buffer above.

### The one assumption, and its fallback

The single left-to-right pass equals `maskflow_core.unmask` only if no
placeholder is a substring of any original value. The mask side guarantees
this (it reserves every placeholder-lookalike found anywhere in the input),
and `StreamingUnmasker` **checks it** at construction. If it ever fails,
the unmasker falls back to buffering the whole response and running
`maskflow_core.unmask` once at `flush()` — correctness over streaming.

### Tool-call argument streaming

`tool_calls[].function.arguments` (OpenAI) and `input_json_delta`
(Anthropic) stream as fragments of a JSON document that is not valid until
complete. The gateway accumulates the fragments, and on block/finish parses
the JSON, unmasks the string leaves, re-serializes, and emits it as one
delta before the finish frame. Clients that concatenate argument deltas
reconstruct the same document.

### The fuzz gate

`tests/streaming/test_unmask_fuzz.py` (run in CI as part of the gateway
job) generates masked texts with tokens, filler, emoji, RTL, ZWJ
sequences, and placeholder-lookalikes as literal content, then asserts —
for **every single byte split point** and for hypothesis-drawn multi-splits
including mid-code-point — that the streamed output equals
`maskflow_core.unmask`.

## Sessions

| | in-process | Redis |
|---|---|---|
| enabled by | default (no `REDIS_URL`) | `MASKFLOW_GATEWAY_REDIS_URL` set |
| scope | one replica | all replicas |
| at rest | never leaves the process | AES-256-GCM (`MASKFLOW_GATEWAY_SESSION_KEY`) |
| TTL | lazy, per-request check | Redis key expiry (authoritative) |

The session snapshot is `maskflow.Session.snapshot()` — the token↔original
mapping plus every identity cache (counters, value→token, numeric
surrogates, reserved tokens). `restore()` rebuilds it so the session keeps
minting placeholders exactly where it left off. This is an additive API
added to `maskflow-sdk` 0.7.0 alongside a `patterns_only` constructor flag
(what `MASKFLOW_GATEWAY_NER=0` uses).

### `maxmemory-policy noeviction`

If Redis evicts a session key mid-conversation, the next `unmask` finds
nothing and the user sees raw `<PERSON_NAME_1>` placeholders. `/readyz`
runs `CONFIG GET maxmemory-policy` and returns **503** unless it is
`noeviction` (set `MASKFLOW_GATEWAY_REQUIRE_MAXMEMORY_NOEVICTION=false` only
for a Redis you have sized to never evict by other means; some managed
Redis blocks `CONFIG GET`, in which case the check is skipped).

## Observability

- **Logs**: JSON (`MASKFLOW_GATEWAY_JSON_LOGS=1`), one object per line.
  Every record additionally passes `maskflow_core`'s `PIIRedactionFilter`
  (pattern/checksum scrub) — a belt-and-braces layer over the gateway's own
  discipline of never logging bodies, only counts / entity types /
  durations / status codes.
- **Metrics** (`/metrics`): `maskflow_detections_total{entity_type,direction}`,
  `maskflow_requests_total{route,provider,status}`,
  `maskflow_errors_total{provider,type}`,
  `maskflow_stage_latency_seconds{stage=mask|upstream|unmask}`,
  `maskflow_active_sessions`. No label carries a value or a session id.
- **Errors**: the error type carries offsets, entity types, counts, and
  stage names only — never a raw value (CLAUDE.md rule 1).

## NER on vs off

`MASKFLOW_GATEWAY_NER=0` (default) runs the pattern/checksum pass plus the
gazetteer (Aho-Corasick Indian-name / address matching) — no spaCy load, no
per-document parse. `=1` adds the full NER pass, catching bare names and
addresses the patterns miss, at roughly 4–5× the cost. `loadtest/README.md`
publishes req/s for both, with the hardware.
