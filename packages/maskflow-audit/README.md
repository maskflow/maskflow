# maskflow-audit

**Find every place your codebase sends text to an LLM — and prove which of those paths leak Indian PII.**

```bash
pip install 'maskflow-cli[audit]'
maskflow audit .
```

```
3 of 5 LLM egress paths masked
1 unmasked · 1 unknown · 3 masked

UNMASKED             tickets/summarize.py:42  openai-client · 0a1b2c3d4e5f
                     from db_column:aadhaar, db_column:pan (+1) · conf: high
...
wrote audit.json
```

`maskflow scan` answers a retrospective question — what PII already reached a
provider, from your logs. This answers the forward one, from your source: **where
can text leave, and is that path guarded?**

- Static discovery over Python via the standard library's `ast` — your code is
  **parsed, never executed**.
- Recognises LLM SDKs (OpenAI, Anthropic, Google, LiteLLM, Cohere, Mistral),
  LangChain and LlamaIndex, raw HTTP to known provider hosts, vector-DB writes
  (Pinecone, Qdrant, Chroma, Weaviate, pgvector), prompt-carrying observability
  exporters (Langfuse, LangSmith, Helicone), and MCP tool results.
- Classifies each path as masked via `mask()`, masked via the MaskFlow gateway,
  masked via a framework integration, unmasked, or **unknown** — and says
  `unknown` rather than guessing.
- Traces each payload back to the DB column, request field or file it came from,
  so a finding names a cause, not just a line number.
- The sink registry is **data** (`sinks/registry.yaml`): adding a provider is a
  YAML edit, not a code change.
- Reports identifiers and counts only — never a value, a string literal's
  contents, or a line of your source.

**Honest about what it is.** Findings in this release are *predicted* from static
analysis. The canary harness that proves a leak by observing a synthetic
identity reach a provider — with the Python call stack captured at send time —
lands next. The report always states which kind of finding you are looking at,
and never calls something a confirmed leak without having watched it happen.

MIT, no telemetry, everything runs locally. Nothing is ever sent to MaskFlow.

Full reference: [`docs/audit.md`](https://github.com/maskflow/maskflow/blob/main/docs/audit.md)
