# Runnable example

A LiteLLM proxy with the MaskFlow guardrail masking every request.

## Run it

```bash
pip install "maskflow-litellm" "litellm[proxy]"
export OPENAI_API_KEY=sk-...
litellm --config packages/maskflow-litellm/examples/config.yaml
# proxy on http://0.0.0.0:4000
```

## 1. PII is masked to the provider, restored to you

```bash
curl -s http://0.0.0.0:4000/v1/chat/completions \
  -H 'Authorization: Bearer sk-1234' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "My PAN is ABCPE1234F. Which ITR form do I file as a salaried employee?"}]
  }'
```

`--detailed_debug` on the proxy shows the upstream request carried
`My PAN is <PAN_1>.` The reply you get back has `ABCPE1234F` in place.
`ABCPE1234F` is a structurally valid but fictitious PAN.

## 2. Streaming round-trips too

```bash
curl -sN http://0.0.0.0:4000/v1/chat/completions \
  -H 'Authorization: Bearer sk-1234' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4o",
    "stream": true,
    "messages": [{"role": "user", "content": "Draft a one-line reply confirming receipt of PAN ABCPE1234F."}]
  }'
```

A placeholder split across SSE chunks is stitched back before it reaches you.

## 3. Stable tokens across a conversation

Send `maskflow_session_id` in metadata (or an `X-Maskflow-Session` header) and
the same value keeps the same `<PAN_1>` token across requests:

```bash
curl -s http://0.0.0.0:4000/v1/chat/completions \
  -H 'Authorization: Bearer sk-1234' -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4o",
    "metadata": {"maskflow_session_id": "demo-conv-1"},
    "messages": [{"role": "user", "content": "Remember my PAN ABCPE1234F."}]
  }'
```
