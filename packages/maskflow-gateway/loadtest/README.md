# Gateway load test

A [Locust](https://locust.io) profile (`locustfile.py`) plus a zero-latency
upstream stub (`mock_upstream.py`) so the numbers measure the **gateway's**
mask/detect/unmask cost and nothing else.

The traffic mix per user: 5 parts non-streaming chat, 3 parts streaming
chat, 2 parts embeddings, 1 part a keyed `/v1/mask` + `/v1/unmask` pair.
Every prompt carries a mix of Indian and generic PII (Aadhaar, PAN, GSTIN,
UPI, IFSC, email, phone, a name, an address) so the detection path is
actually exercised, plus one PII-free prompt.

## Run it

```bash
cd packages/maskflow-gateway

# 1. zero-latency stand-in for the LLM provider
uv run uvicorn loadtest.mock_upstream:app --port 9001 --log-level warning &

# 2. the gateway under test -- pattern/checksum + gazetteer only
MASKFLOW_GATEWAY_OPENAI_BASE_URL=http://127.0.0.1:9001/v1 \
MASKFLOW_GATEWAY_NER=0 \
uv run maskflow-gateway --port 8000 --workers 4 &

# 3. the load
uv run --with locust locust -f loadtest/locustfile.py \
  --host http://127.0.0.1:8000 --headless -u 80 -r 40 -t 60s --only-summary
```

Re-run step 2 with `MASKFLOW_GATEWAY_NER=1` (spaCy model must be installed:
`python -m spacy download en_core_web_sm`) for the NER-enabled number.

## Published numbers

We publish **both**, honestly, and we tell you the hardware — a gateway
number without a CPU spec is marketing, not data.

| Mode | Hardware | Workers | Aggregate req/s | chat (non-stream) req/s | p50 | p95 |
|---|---|---|---|---|---|---|
| pattern-only (`NER=0`) | Intel i7-9750H (6C/12T laptop), 4 workers pinned | 4 | **~430** | ~180 | 100 ms | 330 ms |
| NER-enabled (`NER=1`) | same | 4 | **~90** | ~38 | 120 ms | 1.6 s |

Notes:

- This is a **developer laptop under Locust on the same box** — a dedicated
  4-vCPU cloud instance with the load generator elsewhere does better;
  treat these as a conservative floor and a pattern-vs-NER *ratio* (~4–5×),
  not an SLA.
- The p95 spike with NER on is spaCy model warm-up plus GIL contention
  across the shared work; it settles on a longer run and with more workers.
- The `/v1/mask` + `/v1/unmask` pair runs at sub-25 ms median in both modes
  — the streaming-unmask trie is not a bottleneck; detection is.
- CI runs a short version of this (`gateway-loadtest` job) purely as a
  smoke/regression gate on throughput, not to reproduce the table.
