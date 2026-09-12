# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
for each published package (`maskflow-core`, `maskflow-pack-intl`, `maskflow-sdk`,
`maskflow-gateway`, `maskflow-litellm`, `maskflow-langchain`, `maskflow-llamaindex`,
`maskflow-mcp`, `@maskflow/detection`).

## [Unreleased]

### Added

- **`maskflow-bench` `0.1.0`** (new package) / `maskflow bench --my-data` (#36).
  "Is it accurate on my documents?" had no answer but an argument; now it's
  a command. `maskflow bench --my-data <path>` runs MaskFlow's detector
  against a user's own labelled JSONL file and prints per-entity
  precision/recall/F1 under strict-span and partial-overlap matching.
  - New `maskflow-bench` package: the corpus-agnostic scoring core (JSONL
    loading, label canonicalization, strict/partial-overlap
    precision/recall/F1, JSON/Markdown report writers) extracted from
    `bench/indiapii/harness/`, which wasn't a workspace member and so
    wasn't shipped to `pip install`-ed users. Depends only on
    `maskflow-core` — the five competitor adapters (Presidio,
    mask-privacy, naive-regex, an LLM judge) that made the old location a
    heavy dev-only dependency stay in `bench/`, now reusing this package's
    core instead of duplicating it (also fixes `bench/intlpii/harness/`
    and `bench/scanbench/harness/`, which were already reaching into
    `bench.indiapii.harness`'s internals for the same code).
  - `maskflow_bench.loader`: a lenient schema for a user's own file
    (`text` + `entities[start,end,label]` required; `id`/`domain`/`lang`/
    `value_class` default sensibly) distinct from the bundled corpora's
    stricter format — see [`docs/bench.md`](docs/bench.md).
  - `maskflow bench --my-data PATH [--out DIR] [--limit N]`, registered in
    `maskflow-cli` alongside `doctor`/`explain`/`scan`. **`maskflow-cli`
    `0.7.1` -> `0.8.0`**: new optional `[bench]` extra
    (`maskflow-bench>=0.1.0,<0.2`), lazy-imported by `bench_cmd.py` so a
    bare `pip install maskflow-cli` (and the standalone binary) is
    unaffected.

- **`bench/integrations` — integration-parity gate** (#92 item D). The
  LiteLLM / LangChain / LlamaIndex / MCP wrappers each adapt the masking
  engine to a framework's data shapes; each had unit tests but nothing
  checked, over a realistic PII-dense corpus, that routing text through the
  wrapper masks *exactly* what the core engine does and round-trips
  byte-exact.
  - Routes 300 `indiapii-v1.0` documents through every wrapper's
    framework-free masking layer (LangChain uses the real
    `MaskflowReversibleAnonymizer`) and asserts, per document: the masked
    `(entity_type, value)` set == `maskflow.mask()`'s, the wrapper's own
    unmask restores the document byte-exact, and the masked text fed back
    through the shared `StreamingUnmasker` at 1-byte and random chunk
    splits reassembles exactly. **100% across all four.**
  - These are equality assertions against `core`, not drifting metrics — a
    divergence is a wrapper bug. New `integration-parity` CI job (needs all
    four integration groups; the `benchmark` job deliberately stays lean).
    `make integration-parity`; report
    `bench/reports/integration-parity-v1/results.md`; README "Benchmark"
    section.

- **`bench/scanbench` — `scan-log-v1.0` benchmark for `maskflow scan`** (#92
  item C). Detection is benchmarked on prose (`indiapii-v1.0`,
  `intl-pii-v1.0`); `scan` runs it over log-shaped input — nginx access
  lines, JSON app logs, multi-line stack traces, LLM request dumps, worker
  logs — which nothing measured. This is that shape.
  - **Corpus** (`bench/scanbench/data/scan-log-v1.0.jsonl`): 2000 synthetic
    records, 5 shapes, CC-BY-4.0. PII checksum-valid where a checksum
    exists (self-checked against the packs' validators); hard negatives are
    the PII-lookalike noise real logs carry — request/trace ids, UUIDs, git
    SHAs, epoch-millis, internal `10./172.16./192.168.` IPs in log
    position, `sk_test_`/base64 blobs, `File.java:142` frames.
  - **Harness** (`bench/scanbench/harness/`): reuses the shared scoring
    core; two MaskFlow columns (`detect()` = `--deep`,
    `detect_patterns_only()` = the default fast pass), Presidio + a naive
    log regex as baselines. Headline metric is the **false-positive rate**
    (per 1000 records) — for an exposure audit a false alarm is the
    expensive failure.
  - **Plumbing check**: runs the real
    `maskflow_cli.scan.pipeline.run_pipeline(--deep)` over every record and
    asserts its aggregated per-entity counts equal `detect()`'s — so the
    scan's streaming field-extraction and bounded aggregation are verified
    lossless. Gated in CI (`-m benchmark`).
  - **Findings** (`bench/reports/scan-log-v1.0/results.md`, `docs/scan.md`):
    checksum-validated identifiers are ~100% F1 with near-zero false
    positives on log noise (a naive regex flags 337 fake Aadhaars;
    MaskFlow 0); the `--deep` NER pass produces ~2.5× the false
    `PERSON_NAME` hits the patterns pass does; every internal-range IP is
    reported as `IP_ADDRESS` (no private-IP suppression yet — known gap).
  - **CI**: `bench/baselines-scan.json` + a 2.0-pt F1-regression gate in
    the `benchmark` job; `make rebaseline-bench-scan`.

- **`bench/indiapii/quality` — instrumented for a publishable run** (#92 item
  B). The 200-task LLM-utility benchmark (does masking degrade the model's
  answer?) was built but never run; this makes running it a one-command job
  and records provenance:
  - `run` now writes `meta` into `results.{json,md}` — the exact task-model
    and judge model ids that produced the numbers. A published quality
    figure that doesn't say which models judged it isn't reproducible.
  - `--task-model` / `--judge-model` flags (alternative to the
    `MASKFLOW_BENCH_QUALITY_TASK_MODEL` / `_JUDGE_MODEL` env vars) and
    `--sample-per-type N` for a cheap smoke run across all three task types.
  - `make quality-bench` (haiku task / sonnet judge, ~1200 disk-cached
    calls, ~$1.50) and `make quality-bench-smoke` (~36 calls, ~$0.05).
  - A keyless `claude -p` backend was prototyped and **rejected**: the CLI
    carries Claude Code's own PII-redaction behaviour, so the task model
    emits `<PERSON_NAME_1>`-style tokens itself even in the unmasked
    condition, corrupting the leak-rate metric. The run needs a real API
    endpoint.
  - README "Benchmark" section documents the method; a published run is
    still pending an `ANTHROPIC_API_KEY`.

- **`bench/intlpii` -- `intl-pii-v1.0` benchmark for `maskflow-pack-intl`.**
  The intl pack's 12 international / US-shaped types (EMAIL, PHONE, SSN,
  CREDIT_CARD, IP_ADDRESS, AWS_KEY, API_KEY, JWT, IBAN, ADDRESS,
  PERSON_NAME, DATE_OF_BIRTH) previously had unit-test fixtures but no
  published, reproducible accuracy number -- the one advertised surface
  whose accuracy was asserted, not measured. Item A of the
  benchmark-coverage epic
  ([#92](https://github.com/maskflow/maskflow/issues/92)); the reproducible
  *publishing* pipeline (HuggingFace, doc-site PR, `maskflow bench
  --my-data`) remains [#36](https://github.com/maskflow/maskflow/issues/36).
  - **Corpus** (`bench/intlpii/data/intl-pii-v1.0.jsonl`): 1800 synthetic
    documents across 5 domains (signup form, support ticket, CRM note,
    security incident report, invoice email), CC-BY-4.0. Every value is
    synthetic -- Luhn-valid cards, mod-97-valid IBANs, SSNs in
    real-but-unassigned area ranges, phones in the NANP `555-01xx` fiction
    range -- and `generate.py`'s `self_check()` re-validates every
    checksum-bearing value against the pack's own validators. Deterministic
    from a recorded seed; `test_generator_intl.py` fails if the committed
    corpus drifts from the generator.
  - **Harness** (`bench/intlpii/harness/`): reuses
    `bench.indiapii.harness`'s scoring core wholesale; adds only the intl
    label vocabulary, the Presidio / mask-privacy label maps (both are real
    competitors on generic PII), and an intl naive-regex baseline. The
    `mask_privacy` adapter calls the scanner with a no-op `encode_fn` so
    its stateful format-preserving-encryption vault (which raised
    `TokenCollisionError` on ~980 of 1800 docs via the convenience wrapper)
    does not corrupt a detection-only measurement.
  - **Results** (`bench/reports/intl-pii-v1.0/results.md`): per-entity
    strict + partial F1 for all 12 types vs stock Presidio, mask-privacy,
    and a naive regex, plus latency/memory. MaskFlow leads on the
    structured/validated types and the secret types neither competitor
    detects; Presidio and mask-privacy are ahead on `PERSON_NAME`, and
    mask-privacy on `DATE_OF_BIRTH` -- shown, not hidden, in the README
    benchmark section.
  - **CI**: `bench/baselines-intl.json` + a 2.0-point F1-regression gate
    (`test_ci_regression.py`, maskflow adapter only, 300-doc subset) wired
    into the `benchmark` job. `make rebaseline-bench-intl` to update it.

- **`maskflow-mcp` `0.1.0` / `0.1.1`** -- a new package: a [Model Context
  Protocol](https://modelcontextprotocol.io) proxy that wraps any MCP
  server. It masks PII in outbound `tools/call` arguments before they reach
  the backend tool and restores it in the results, with placeholders that
  stay consistent for a whole agent run. Closes issue
  [#39](https://github.com/maskflow/maskflow/issues/39) (item 4, the last).
  `0.1.1` adds `server.json` and the `mcp-name` README marker so
  `release-mcp.yml` also publishes the entry to the official MCP Registry
  (`registry.modelcontextprotocol.io`, `io.github.maskflow/mcp`) via OIDC.
  - **`maskflow-mcp` CLI** -- `maskflow-mcp stdio --backend "<cmd>"` (or
    `--config <claude-desktop.json> --backend-name <n>`), `maskflow-mcp http
    --backend <url> --port <n>`. Flags: `--min-confidence`,
    `--patterns-only`, `--mask-tool-results` (off by default -- also mask
    PII the tool *introduced*, not just unmask what it echoed),
    `--session-ttl`, `--pass-env`.
  - **`MaskflowMiddleware`** -- a `fastmcp` middleware (`on_call_tool`) that
    walks the arguments dict (string / numeric values only, keys never) via
    `Session.mask_json`, forwards the masked call, then unmasks the
    `ToolResult` text and `structured_content`. `build_proxy(backend)`
    wires it onto `FastMCP.as_proxy(...)`.
  - **Sessions** -- one `maskflow.Session` per MCP connection (keyed by
    session id; a constant for stdio), so identity is stable across every
    tool call; in-memory only, never logged.
  - `tools/list`, `prompts/*`, `resources/*` pass through unchanged.
  - `fastmcp` (`>=2.11,<3` -- the line that builds on the stable `mcp` 1.x
    SDK and does not bundle LLM vendor SDKs) is a runtime dependency,
    installed in the workspace only by `uv sync --group mcp`, with a
    dedicated CI job. `maskflow_mcp._masking` has no `fastmcp` import. Ships
    `py.typed`. `release-mcp.yml` on `mcp-v*` tags. Runnable example,
    `docs/mcp.md`, README + CHANGELOG.

- **`maskflow-llamaindex` `0.1.0`** -- a new package: MaskFlow for
  [LlamaIndex](https://github.com/run-llama/llama_index). Covers **item 3 of
  [#39](https://github.com/maskflow/maskflow/issues/39)**.
  - **`MaskflowNodePostprocessor`** -- a drop-in for
    `llama_index.core.postprocessor.PIINodePostprocessor` that masks PII in
    retrieved nodes before the synthesizer. Same `mask_pii()` /
    `_postprocess_nodes()` contract, same `__pii_node_info__` metadata key
    and embed/LLM exclusions, so an existing unmask step keeps working. No
    LLM call, no HuggingFace model. `consistent_across_nodes=True` (the
    default) shares one `maskflow.Session` across every node in a call, so
    `<PERSON_NAME_1>` is the same person in every chunk --
    `PIINodePostprocessor` numbers each node independently. `mask_query=True`
    masks the query through the same session.
  - **`MaskflowIngestionTransform`** -- a `TransformComponent` that masks
    node text at ingestion, so raw PII is never embedded or written to the
    vector store. Default `strategy="redact"` is non-reversible by design
    (no map to persist); `surrogate` / `replace` and an opt-in
    `store_mapping` (which warns) are available.
  - **`unmask_response` / `collect_node_mapping` / `response_unmasker` /
    `MaskflowQueryEngine`** -- restore the originals in the synthesized
    answer (string or streamed) from the per-node maps.
  - `llama-index-core` (`>=0.12,<1`) is a runtime dependency; in the
    workspace it is only installed by `uv sync --group llama-index` (large
    dep tree), with a dedicated CI job. `maskflow_llamaindex._masking` has
    no `llama_index` import. Ships `py.typed`. `release-llamaindex.yml` on
    `llamaindex-v*` tags. Runnable example, `docs/llamaindex.md`, README.

- **`maskflow-langchain` `0.1.0`** -- a new package: MaskFlow for
  [LangChain](https://github.com/langchain-ai/langchain).
  - **`MaskflowReversibleAnonymizer` / `MaskflowAnonymizer`** -- drop-in
    replacements for `langchain_experimental.data_anonymizer`'s
    `PresidioReversibleAnonymizer` / `PresidioAnonymizer`. Same method
    names, signatures, and return shapes a chain touches (`.anonymize`,
    `.deanonymize`, `.reset_deanonymizer_mapping`, `.deanonymizer_mapping` /
    `.anonymizer_mapping` in the nested `{ENTITY: {anon: original}}` shape,
    JSON/YAML `save`/`load`), so migrating is one import line. The
    reversible one holds a long-lived `maskflow.Session`, so a value keeps
    its placeholder across every `.anonymize()` call. `add_recognizer` and
    `add_operators` take MaskFlow-native arguments (documented).
  - **`MaskflowDeanonymizer`** -- a streaming-aware `Runnable[str, str]`
    (`anonymizer.deanonymizer`) for the chain tail. Unlike Presidio's
    `RunnableLambda(deanonymize)`, it restores originals chunk by chunk
    under `chain.stream()` via `maskflow.streaming.StreamingUnmasker`, so a
    placeholder split across chunks is stitched. Fuzzed over arbitrary
    chunk sizes.
  - **`MaskflowLeakGuardCallback`** (+ async) -- a callback that tallies PII
    crossing the LLM boundary by entity type and count, never values
    (`.summary()`), and with `raise_on_prompt_pii=True` raises
    `MaskflowPIILeakError` before the model is called so a forgotten
    anonymizer fails closed.
  - Covers **item 2 of
    [#39](https://github.com/maskflow/maskflow/issues/39)**. `langchain-core`
    (`>=0.3,<2`) is a real dependency; tests run in the normal CI matrix.
    Runnable example under `packages/maskflow-langchain/examples/`, design
    notes in `docs/langchain.md`.

- **`maskflow-litellm` `0.1.0`** -- a new package: a
  [LiteLLM](https://github.com/BerriAI/litellm) custom guardrail
  (`maskflow_litellm.MaskflowGuardrail`) that masks PII before a request
  leaves the proxy and restores it in the response. Point a `config.yaml`
  guardrail at it with `mode: [pre_call, post_call]`.
  - **Round-trip**: `async_pre_call_hook` masks `messages[].content`
    (prose, multimodal text parts, Anthropic blocks), Anthropic `system`,
    and `tool_calls[].function.arguments` (JSON walk -- string/number
    *values* only, keys never); `async_post_call_success_hook` restores the
    non-streaming response (OpenAI `ModelResponse` + Anthropic native
    message dict). Inbound tool results are masked *through* the session,
    never unmasked toward the model.
  - **Streaming**: `async_post_call_streaming_iterator_hook` restores
    `delta.content` and `tool_calls[].function.arguments` fragments with
    the shared `StreamingUnmasker` (see below), so a placeholder split
    across chunks is stitched back before the caller sees it. Fuzzed
    against arbitrary chunk boundaries.
  - **Sessions**: token identity is stable for one request always;
    cross-turn identity via a `maskflow_session_id` metadata field or an
    `X-Maskflow-Session` header. In-process TTL store by default (correct
    for a single-worker proxy); an optional `[redis]` extra adds an
    AES-256-GCM-encrypted snapshot store for multi-worker / multi-replica
    proxies.
  - **PII safety**: the token<->value map is held in memory only (or
    encrypted in Redis); only an opaque session ref reaches request
    metadata; no mapping or original value is ever logged. `-m leak` gate.
  - **Detection**: MaskFlow's full engine, so the India identifiers
    (Aadhaar, PAN, GSTIN, UPI, IFSC, ABHA, Indian names/addresses, ...)
    are covered alongside the generic PII. `maskflow_patterns_only: true`
    skips the spaCy NER pass for latency.
  - `litellm` is a peer dependency (the proxy provides it); the
    provider-agnostic logic is tested `litellm`-free, the `CustomGuardrail`
    adapter against the real base class via `uv sync --group litellm`.

- **`maskflow-sdk` `0.8.0`** -- `maskflow.streaming` (`StreamingUnmasker`,
  `unmask_whole`) moved here from `maskflow-gateway` so every `Session`
  consumer (the gateway, the LiteLLM guardrail, any custom integration)
  builds a streamed unmasker from one fuzz-tested implementation.
  `maskflow_gateway.streaming.unmask` is now a re-export shim -- no gateway
  API change. Also ships a `py.typed` marker.

- **`maskflow-gateway`** -- `streaming/unmask.py` re-exports
  `maskflow.streaming`; requires `maskflow-sdk>=0.8.0`. No behaviour
  change.

- **`maskflow-gateway` `0.1.0`** -- a new package: a drop-in
  OpenAI/Anthropic-compatible reverse proxy (FastAPI + uvicorn) that masks
  PII before a request reaches the provider and restores it in the
  response, **including mid-stream**. Point an existing client's base URL
  at it; no SDK or code change.
  - **Endpoints**: `POST /v1/chat/completions` (OpenAI, streaming +
    non-streaming, tool calls), `POST /v1/messages` (Anthropic, streaming +
    tool use), `POST /v1/embeddings` (masks each input *before* it is
    embedded -- the RAG path), `POST /v1/mask` / `POST /v1/unmask` (direct,
    no upstream), `GET /healthz` `GET /readyz` `GET /metrics`
    `GET /v1/entities`. The client's own provider key is forwarded
    untouched and nothing is stored unless
    `MASKFLOW_GATEWAY_UPSTREAM_API_KEY` is explicitly set.
  - **Streaming unmask**: the model may split `<PERSON_NAME_1>` across SSE
    chunks (and across frames, with JSON/protocol punctuation between the
    halves). The gateway parses the provider SSE, and a `StreamingUnmasker`
    -- a rolling buffer + a trie of the session's active placeholders --
    emits the longest prefix that cannot extend into any placeholder,
    retaining only the tail that still could, bounded by max placeholder
    length, flushing at stream end. A two-layer decoder
    (`ByteStreamingUnmasker`) handles chunk splits mid-UTF-8. Fuzz-tested:
    the concatenated stream equals `maskflow_core.unmask` for **every**
    byte-boundary chunking, including mid-code-point (`pytest -m` gate in
    the `gateway` CI job). A whole-response `unmask` fallback covers the
    (mask-side-precluded) case of a placeholder being an infix of an
    original.
  - **Tool calls**: `tool_calls[].function.arguments` /
    `input_json_delta` are walked as JSON -- string leaves masked, keys
    never touched, types preserved, depth + size bounded; streamed
    argument fragments are accumulated and emitted unmasked as one delta.
    Inbound `tool_result` / `role:"tool"` content is masked through the
    session (never unmasked toward the model), so placeholder identity
    stays consistent across a whole agent run.
  - **Sessions**: `X-Maskflow-Session: <opaque id>` opts into cross-turn
    token identity; absent -> a fresh ephemeral session per request. Redis
    backend (`maskflow-gateway[redis]`) with **AES-256-GCM** encryption of
    the session mapping at rest (`MASKFLOW_GATEWAY_SESSION_KEY`), mandatory
    TTL (default 1 h, per-request `X-Maskflow-Session-TTL` capped at 24 h),
    and a `maxmemory-policy != noeviction` check that makes `/readyz`
    return **503 fail-closed** (eviction mid-conversation = failed unmask =
    raw placeholders shown to a user).
  - **Ops**: JSON logs through `maskflow_core`'s PII scrub filter;
    Prometheus metrics (`maskflow_detections_total{entity_type,direction}`,
    `maskflow_requests_total`, `maskflow_errors_total`,
    `maskflow_stage_latency_seconds{stage=mask|upstream|unmask}`); request
    size limit, upstream timeouts, per-key token-bucket rate limiting.
    Error bodies carry offsets / entity types / stage names only, never a
    raw value.
  - **Deploy** (`packages/maskflow-gateway/deploy/`): multi-arch
    `Dockerfile`, `docker-compose.yml` (gateway + noeviction Redis), a Helm
    chart with HPA / PDB / ServiceMonitor / probes / non-root hardening,
    and Fly / Render / Railway templates. `release-gateway.yml` publishes
    `maskflow-gateway` to PyPI (OIDC) and `ghcr.io/maskflow/gateway`
    (`amd64` + `arm64`) on a `gateway-v*` tag.
  - **Load test** (`packages/maskflow-gateway/loadtest/`): a Locust profile
    + zero-latency upstream stub. Published numbers, with the hardware:
    **~430 req/s** pattern-only and **~90 req/s** NER-enabled on an Intel
    i7-9750H laptop, 4 workers -- a conservative floor and a ~4-5x
    pattern-vs-NER ratio, not an SLA. New CI jobs `gateway`, `gateway-helm`,
    `gateway-loadtest`.
  - `docs/gateway.md` covers the request flow, the streaming algorithm, and
    the `noeviction` requirement in full.
- **`maskflow-sdk` `0.7.0`** (additive, no breaking change):
  - `Session.snapshot() -> bytes` / `Session.restore(bytes)` -- serialize
    the full masking state (mapping + every identity cache) so a session
    can move between processes. `Session.mapping` property exposes the live
    `Mapping` (for building an incremental unmasker). `Session(...,
    patterns_only=True)` / `session(patterns_only=True)` skip the NER pass
    (routes through `detect_patterns_only`) -- the same
    coverage/speed tradeoff `maskflow_core.logging_filter` makes. All
    additive; `mask()` / `unmask()` / `mask_and_call()` and the existing
    `Session` API are unchanged (`test_api_signatures.py` still green).
- `maskflow-core`: `resolve_config()` now ignores env vars under the
  `MASKFLOW_GATEWAY_*` sub-namespace (owned by `maskflow-gateway`'s own
  settings) instead of flagging them as malformed `.maskflowrc` config.

- `maskflow-cli` `0.6.0`: `maskflow scan` -- a retrospective PII-exposure
  scanner that answers "what PII has this system already sent to third-party
  LLM providers?". Reads historical LLM traffic through one of eight source
  adapters (`jsonl`/`ndjson` with `--field` selectors, `csv` with
  `--columns`, `dir` recursive, `s3` streamed, `postgres` server-side
  cursor, and the `langfuse` / `helicone` / `langsmith` REST APIs), streams
  it through MaskFlow's own detection with bounded memory (`--workers N`,
  resumable via a `--checkpoint` file), and writes **one self-contained HTML
  report** (inline CSS/JS, zero external requests -- it is meant to be
  emailed to auditors) with a single headline number, breakdowns by entity
  type / provider / service / time, a severity ranking with a plain-English
  "why this matters" per row, masked excerpts only (never a raw value), and
  a DPDP Rule 6 mapping appendix slot. Also `--format json|csv`. Detection
  is hybrid: the pattern/checksum pass runs over the whole corpus (the
  1 GB / 5 min target) while the NER pass (bare Indian names & addresses)
  runs on a `--sample` and is reported as a clearly-labelled extrapolated
  estimate; `--deep` forces the full pipeline over every record. A
  permanent CI fuzz gate (`scan-fuzz`) generates a corpus of known
  synthetic PII, renders the report, and asserts no raw value survives in
  any output format. New CLI dependency `httpx` (API sources); `boto3` /
  `psycopg` gated behind `maskflow-cli[s3]` / `[postgres]`. No change to
  `maskflow-core`, `maskflow-sdk`, or the existing CLI commands. Ships a
  runnable example -- `packages/maskflow-cli/examples/sample-llm-traffic.jsonl`
  (60 fully synthetic records) plus `examples/README.md` and the
  `generate_sample.py` that produced it -- with a quick-start in the CLI
  README.
  - **Packaging**: `release-cli.yml` now also builds and pushes
    `ghcr.io/maskflow/cli` (`linux/amd64` + `arm64`, spaCy + model baked
    in) and PyInstaller standalone binaries for mac/linux/windows (attached
    to the GitHub Release; spaCy excluded, so the binary runs the
    pattern/checksum pass only and `--deep` points at the pip/Docker
    install). `packaging/scan-action/` is a composite GitHub Action that
    runs `maskflow scan` in CI, uploads the report, and can fail the job
    over a PII-instance threshold. New CI jobs `scan-binary` (spec /
    entry-point / multiprocessing-freeze regression guard) and
    `scan-docker` (Dockerfile-change smoke build). `docs/scan.md` gains an
    Install section; `packages/maskflow-cli/packaging/README.md` documents
    each channel.
  - **DPDP Rule 6 appendix**: the report's Appendix A now carries a draft
    mapping of each Rule 6 safeguard to what the scan / MaskFlow
    contributes (explicitly a starting point, not legal advice), keeping
    the `<!-- DPDP_RULE6_APPENDIX -->` marker for a deployment's own text.
    See `docs/dpdp-rule6.md`.
  - Excerpts now blank any date-shaped token (`<DATE>`) regardless of the
    NER pass -- a date next to an identity document is very likely a DOB,
    and `DATE_OF_BIRTH` is NER-only, so a patterns-only run (the binary, or
    any host without spaCy) no longer surfaces a raw birth-date.
- `bench/indiapii/quality`: a 200-task LLM-judged quality benchmark
  answering "does masking India PII before an LLM call cost task quality,
  and does it cost more with typed placeholders than with plausible
  surrogates?" Tasks (summarize / draft_reply / extract_fields) are sampled
  from the existing `indiapii-v1.0` corpus and run under three conditions
  -- unmasked, masked-with-placeholders (`Strategy.REPLACE`), and
  masked-with-surrogates (`Strategy.SURROGATE`) -- through the real
  `mask_with_policy()`/`unmask()` round trip. Each final (post-unmask)
  response is scored by a fixed-rubric LLM judge (task_completion, fluency,
  factual_consistency, 1-5 each, tool-use structured output) plus
  deterministic field-accuracy P/R/F1 for extract_fields (against the
  corpus's own gold spans) and a placeholder-leak check. Both the task
  model and judge model are env-configurable
  (`MASKFLOW_BENCH_QUALITY_TASK_MODEL` / `..._JUDGE_MODEL`, default Sonnet
  5 / Opus 5) and every LLM call is disk-cached, so a rerun with no new
  tasks makes zero API calls. `uv run python -m bench.indiapii.quality
  generate-tasks|run`. CI runs the pure/deterministic pieces (task
  generation, scoring, cache, masking pipeline against a fake model) with
  no Anthropic key; the live task-model/judge path is manual-only, same as
  `bench/indiapii/harness/adapters/llm_adapter.py`'s own network call.
- `maskflow-pack-india` (still unreleased `0.5.0`, no separate bump): adds
  `Strategy.SURROGATE` generators for all 16 of this pack's registered
  types (`surrogates.py`) -- previously `SURROGATE` silently fell back to
  the same typed placeholder as `Strategy.REPLACE` for every India type
  (no generator was registered, per `masking.py`'s documented fallback).
  Each generator produces a fresh checksum-valid (Verhoeff/GSTIN/MRZ, where
  a checksum exists) or format-valid value drawn from this pack's own
  bundled reference data (IFSC bank codes, RTO codes, UPI PSP handles,
  city/state/name gazetteers) -- never a real-world-registry lookup, same
  "random within the valid shape" discipline `bench/indiapii/generator/
  identifiers.py` already uses to build the synthetic benchmark corpus.
  Built for `bench/indiapii/quality`'s masked-with-surrogates condition,
  but registered unconditionally, so any caller selecting
  `Strategy.SURROGATE` for an India type now gets a real surrogate instead
  of the `REPLACE` fallback.
- `scripts/refresh_india_reference_data.py` and `docs/data-refresh.md`
  (issue #28): closes the one item on that issue with zero prior progress --
  every `maskflow-pack-india` reference-data file documented its own refresh
  procedure as prose, but nothing was scripted or consolidated. The script
  has `ifsc`/`cities` subcommands, each a pure diff function (unit-tested in
  `packs/maskflow-pack-india/tests/test_reference_data_refresh.py`, no
  network) plus a fetch/parse wrapper; it never writes the bundled data
  files itself, matching the "curated, not auto-merged" philosophy those
  files already documented. `upi` prints the still-manual PSP-handle
  procedure -- no machine-readable NPCI feed exists. `docs/data-refresh.md`
  is the single doc covering sourcing/licensing/refresh cadence for all five
  data files (IFSC codes, UPI handles, RTO codes, place gazetteer, name
  gazetteer); each file's docstring now points to it instead of duplicating
  the procedure prose.
- `maskflow-core` (still unreleased `0.6.0`, no separate bump -- see the
  `0.5.0` -> `0.6.0` entry below): also adds `maskflow_core.logging_filter`
  (closes the last open item on issue #23) -- `PIIRedactionFilter`, a
  `logging.Filter` that scrubs a LogRecord's formatted message through the
  new `detect_patterns_only()` (regex/checksum-validated patterns, no NER --
  cheap enough for a hot logging path) before emission, and
  `install_pii_filter(logger=None, ...)` to attach one (default: root
  logger; idempotent per logger). Opt-in only -- importing `maskflow_core`
  never touches global logging state on its own. This protects a *downstream
  app's own* logger calls (e.g. `logger.info(f"...{raw_input}")` before
  `mask()` ever runs, or a careless third-party recognizer plugin doing
  `logger.debug(span.text)`), which repr-exclusion and the `pytest -m leak`
  gate never covered -- those two only protect MaskFlow's own test session.
  `detect_patterns_only()` is also now public on `detect.py`/`maskflow_core`
  (the existing tier-0-excision computation inside `detect()`, factored out
  and reused rather than duplicated). NER-only entity types (bare names,
  addresses) and `exc_info`/traceback text are explicitly out of scope --
  see `docs/logging.md`.
- `maskflow-core` `0.5.0` -> `0.6.0`: adds `maskflow_core.recognizer` (issue
  #21's pluggable recognizer architecture) -- a `Recognizer` ABC
  (`entity_type`/`supported_languages`/`default_threshold`/
  `analyze(text, ctx) -> Iterable[Span]`), `AnalysisContext` (per-`detect()`-
  call state including a lazily computed, memoised NLP doc -- however many
  NER-dependent recognizers share one context, the underlying parse happens
  exactly once), three base helpers (`PatternRecognizer`,
  `GazetteerRecognizer`, `NlpRecognizer`) covering the three match
  strategies core already supported, and `RecognizerRegistry` (lazy
  discovery via the `"maskflow.recognizers"` entry-point group -- enumerating
  entry points never imports a pack; only actually accessing
  `.recognizers`/`.register_all()` does). `Recognizer.register()` populates
  the *existing* `PATTERNS`/`CUSTOM_RECOGNIZERS`/`NER_RECOGNIZERS` dicts
  `detect()`/`detect_ner()` already read, and is idempotent per instance --
  detection.py/ner.py's resolution pipeline is otherwise unchanged. Purely
  additive: no existing function's signature changed, `register_pattern()`/
  `register_custom_recognizer()`/`register_ner_recognizer()` still work
  exactly as before. `docs/custom-recognizers.md` added.
- `maskflow-pack-intl` `0.2.0` -> `0.3.0` and `maskflow-pack-india` `0.3.0`
  -> `0.4.0`: internal registration migrated from bare
  `register_pattern()`/`register_custom_recognizer()`/
  `register_ner_recognizer()` calls to declarative `PatternRecognizer`/
  `GazetteerRecognizer`/`NlpRecognizer` objects, and both packs now expose a
  `load_recognizers()` entry point (group `"maskflow.recognizers"`) for
  `RecognizerRegistry`-based discovery. **Behavior-identical**: each pack's
  `__init__.py` still registers everything at import time exactly as
  before (same patterns, same confidences, same context-keyword unions, same
  order) -- verified by the full existing test suite (both packs' positive/
  negative/hard-negative fixtures, `-m leak`, `-m benchmark`) passing
  unchanged. Both packs now require `maskflow-core>=0.6.0,<0.7`. Explicitly
  out of scope for this round: `maskflow-sdk`/`maskflow-cli` still activate
  both packs via the original side-effect `import maskflow_pack_intl` /
  `import maskflow_pack_india` (unchanged) rather than
  `RecognizerRegistry`-based discovery -- migrating their activation
  mechanism is a separate, later decision, not required for this issue's
  scope (the pluggable interface itself, and packs being *capable* of
  entry-point discovery).
- `maskflow-sdk` `0.4.0` -> `0.5.0` and `maskflow-cli` `0.3.0` -> `0.4.0`:
  no code changes in either package -- dependency bounds widened for the
  `maskflow-core`/`maskflow-pack-intl`/`maskflow-pack-india` bumps above
  (`maskflow-core` floor raised to `0.6.0` since the packs now hard-require
  `maskflow_core.recognizer`), so this bump exists purely to publish those
  widened bounds as a new release.

### Changed

- **Benchmark reports: a genuine `0.0` F1 now renders as `0.0%`, not `—`**
  (#92 item F). `PRFResult.f1` collapsed a measured zero (the detector
  fired on a type but matched no gold span -- e.g. `INDIAN_ADDRESS` strict,
  where no adapter's multi-token span boundaries ever line up exactly) to
  `None`, making it indistinguishable from "not scored" in the tables. It
  now returns `0.0` when precision and recall both have a denominator;
  `None` is reserved for "F1 is undefined" (no predictions for the type at
  all, or no gold). `bench/reports/{indiapii,intl-pii,scan-log}-v1.0/`
  regenerated -- `INDIAN_ADDRESS` / `ADDRESS` strict cells that read `—` now
  read `0.0%`, and the India report picks up `mask-privacy` 4.3.0 (Indian
  address partial F1 57.9% -> 50.5%, person name 37.7% -> 30.4%); README
  benchmark table updated to match. #92 item E (JS<->Py cross-language
  parity) was dropped.

- Dependency bounds widened for the released `maskflow-sdk` `0.9.0` (no code
  change): `maskflow-litellm` / `maskflow-langchain` / `maskflow-llamaindex`
  now allow `maskflow-sdk <0.10`. Published as patch bumps -- `0.1.0` ->
  `0.1.1` for all three -- since the fix sat in `pyproject.toml` unreleased
  for days (found by auditing every package's post-tag commits, not by
  design): a bare `pip install maskflow-litellm` (or `-langchain` /
  `-llamaindex`) was pinning `maskflow-sdk==0.8.0` despite `0.9.1` being
  current, and combining any of the three with `maskflow-gateway` `0.2.0`
  (`maskflow-sdk>=0.9.0,<0.10`) in one environment was
  `ResolutionImpossible`. `maskflow-mcp` `0.1.1` -> `0.1.2` for the same fix
  (it independently picked up the same stale `<0.9` bound).

- `maskflow-sdk` `0.2.0` -> `0.3.0`: now depends on `maskflow-pack-india`
  (`>=0.1.0,<0.2`) in addition to `maskflow-pack-intl`, registered the same
  side-effect-import way in `maskflow/__init__.py`. This is a **behavior
  change, not just a new capability**: text that previously passed through
  `mask()` untouched because it merely *looked like* an Aadhaar/PAN/GSTIN/
  IFSC/UPI VPA will now be masked. `mask()`/`unmask()`/`mask_and_call()`'s
  signatures are unchanged (CLAUDE.md rule 4), so this is additive at the
  API level and a minor version bump, not a major one.
- `maskflow-cli` `0.1.0` -> `0.2.0`: now also depends on `maskflow-pack-india`
  (`>=0.1.0,<0.2`), registered in `app.py` the same way as `maskflow-pack-intl`.
  `maskflow doctor` and `maskflow explain` are entirely registry-driven, so
  no command-specific code changed -- the 6 India entity types just start
  showing up in `doctor`'s entity table and `explain`'s pattern hits.
  `maskflow config validate`'s soft entity-name cross-check now recognizes
  `entities.AADHAAR`/`PAN`/`GSTIN`/`IFSC`/`UPI_VPA` as known types instead
  of warning on them. Also removes `doctor.py`'s now-dead "maskflow-pack-
  india not installed" hint, since it's a hard dependency now, not an
  optional one to nudge users toward installing.
- `maskflow-pack-india` `0.1.0` -> `0.2.0`: adds the 9 new entity types
  listed below (INDIAN_MOBILE through BANK_ACCOUNT_IN) -- additive only, no
  API change. `maskflow-sdk` and `maskflow-cli`'s `maskflow-pack-india`
  dependency bound widened from `<0.2` to `<0.3` so a future release of
  either can pick up this version; their own published versions on PyPI
  still declare the old `<0.2` bound until they're next released.
- `maskflow-core` `0.4.0` -> `0.5.0`: adds `registry.register_custom_recognizer()`
  alongside the existing `register_pattern`/`register_ner_recognizer` --
  lets a pack register a non-regex match source (e.g. a gazetteer
  automaton) that still goes through the same validator/context-boost/
  tier-0-excision/resolve pipeline as every other recognizer. Also adds
  `NerMapping.agreement_boost` (default `0.0`, so every existing NER
  registration is unaffected) and `detect_ner()`'s new `agreement_spans`
  keyword: when a spaCy entity overlaps a pattern/custom-recognizer
  candidate of the same type (even one that scored below its own
  threshold), `agreement_boost` is added to its confidence before the
  context boost -- `detect()` now passes every pattern-pass candidate
  through as agreement evidence. Both additions are purely additive; no
  existing function's signature changed, no existing recognizer's output
  changed (agreement_boost only has an effect when a pack explicitly opts
  in). `maskflow-sdk`, `maskflow-cli`, and `maskflow-pack-intl`'s
  `maskflow-core` dependency bound widened from `<0.5` to `<0.6`.
- `maskflow-pack-india` `0.2.0` -> `0.3.0`: adds PERSON_NAME (Indian) and
  INDIAN_ADDRESS across all three built layers (L1 gazetteer, L2
  structural, L3 NLP agreement -- L4 fine-tuning not started, see Added
  below and the cumulative precision/recall report). Now depends on
  `pyahocorasick` and `maskflow-core[nlp]` (spaCy -- previously spaCy-free)
  `>=0.5.0,<0.6`. `PIN_CODE`'s state/UT name list moved from `__init__.py`
  to `data/indian_places.py` (now shared with INDIAN_ADDRESS's gazetteer)
  -- same 36 values, no behavior change. `maskflow-sdk`/`maskflow-cli`'s
  `maskflow-pack-india` bound widened from `<0.3` to `<0.4`.
- **Behavior change for `maskflow-pack-intl`'s PERSON_NAME when
  `maskflow-pack-india` is also installed** (i.e. the actual
  `maskflow-sdk`/`maskflow-cli` bundled configuration): pack-india's L3
  registers the same spaCy `"PERSON"` label pack-intl does
  (`register_ner_recognizer`'s `NER_RECOGNIZERS` dict holds one mapping
  per label; pack-india imports after pack-intl in the bundled
  configuration, so its registration wins). The standalone base confidence
  (`0.75`) is unchanged from pack-intl's own -- deliberately NOT
  down-weighted, to avoid regressing non-Indian-name recall -- but a name
  that also matches this pack's L1 gazetteer or L2 structural patterns now
  scores higher (`0.75` -> `0.95`) and records that agreement in
  `span.explanation`.
- `maskflow-sdk` `0.3.0` -> `0.4.0` and `maskflow-cli` `0.2.0` -> `0.3.0`:
  no code changes in either package -- both already declared
  `maskflow-pack-india>=0.1.0,<0.4` and `maskflow-core>=0.5.0,<0.6` (widened
  earlier in this same round of changes, see above), so this bump exists
  purely to publish those already-widened bounds as a new release. Since
  `maskflow-pack-india<0.4` and `maskflow-core<0.6` already permitted
  0.3.0/0.5.0, this is what actually lets `pip install maskflow-sdk`/
  `maskflow-cli` pick up PERSON_NAME (Indian)/INDIAN_ADDRESS -- their
  previously-published versions (`0.3.0`/`0.2.0`) are unaffected and still
  resolve to the pre-this-session `maskflow-pack-india`/`maskflow-core`.
  Minor bump, not patch, for the same reason earlier pack-india dependency
  bumps in this file were treated as minor: `mask()`'s output changes for
  previously-untouched text (new entity types get masked that weren't
  before), even though neither package's own API changed.

### Added

- New package `maskflow-pack-india` (`packs/maskflow-pack-india`, `0.1.0`,
  published to PyPI): AADHAAR (12-digit UID and
  16-digit VID, Verhoeff checksum), AADHAAR_MASKED (display-masked form,
  e.g. `XXXX XXXX 9012`, unvalidated/context-gated), PAN (structural
  holder-category check; no public checksum exists for the final letter),
  GSTIN (state-code range + embedded-PAN structural check + base-36
  checksum -- also emits the embedded PAN as its own candidate span, which
  `spanset.py`'s containment resolution correctly drops in favor of the
  longer GSTIN), IFSC (bank code checked against a bundled, documented-
  refresh-procedure RBI code list), and UPI_VPA (PSP handle checked against
  a bundled NPCI handle list; a `handle@domain.tld` that isn't a known PSP
  handle is left alone so a general email recognizer claims it instead).
  Positive context keywords are English, Hindi (Devanagari), and Hinglish
  transliterations; core has no negative-context ("example"/"test"/"dummy"
  suppression) mechanism yet, so that part of CLAUDE.md's confidence
  formula isn't implemented for this pack either -- noted as follow-up work.
- `maskflow-pack-india`: 9 more India entity types -- INDIAN_MOBILE (`+91`/
  `0`-prefixed numbers get full confidence unconditionally; a bare 10-digit
  number needs a nearby context keyword), PIN_CODE (unvalidated, always
  context-required -- pin/pincode/a state or UT name/address), VOTER_ID
  (EPIC number, structural only, no public checksum), INDIAN_PASSPORT
  (the inline 8-char number, structural only, plus a full TD3
  machine-readable-zone block recognizer validated against all 4 ICAO 9303
  check digits -- document number, DOB, expiry, and composite), DRIVING_LICENCE
  and VEHICLE_REG (both validated against a bundled, documented-refresh-
  procedure state/UT RTO code list), ABHA_NUMBER (unvalidated, always
  context-required, no checksum), ABHA_ADDRESS (`handle@abdm`/`handle@sbx`,
  same design as UPI_VPA), and BANK_ACCOUNT_IN (9-18 digits, unvalidated,
  always context-required). Every context-required type ships a dedicated
  hard-negative test asserting zero detections on invoice/order-ID/
  timestamp text of the same digit shape.
- `maskflow-pack-india`: PERSON_NAME (Indian) and INDIAN_ADDRESS, built
  through **L1 gazetteer, L2 structural, and L3 NLP-agreement** (L4
  fine-tuning NOT started -- measured recall after L1-L3 is well above the
  work order's 0.85 gate, see the report below).

  **L1 (gazetteer):** new `gazetteer.py` matches a ~115k-entry Indian name
  gazetteer and a 368-entry state/UT + city gazetteer via `pyahocorasick`
  (lazily built + `lru_cache`d, so bare `import maskflow_pack_india` stays
  fast), routed through the new `register_custom_recognizer()` core hook.
  PERSON_NAME contiguous hits (e.g. a given name immediately followed by a
  surname) coalesce into one span; frequency-tiered confidence (common
  names/words need nearby context, rarer ones fire standalone); a small
  programmatic spelling-variant rule table (Krishna/Krishnaa, Lakshmi/
  Laxmi); English- and Hinglish-function-word and this pack's own
  entity-name-acronym collisions (`the`, `mera`, `abha`, `pan`, ...)
  excluded/downgraded -- see `data/indian_names.py`'s docstring.
  INDIAN_ADDRESS's gazetteer alone is deliberately low-confidence (a bare
  place mention isn't an address).
  Gazetteer sourcing fell short of the 150k-name target: the largest
  license-clean candidate found (`swami93/indian-names-1.5M` on
  HuggingFace, MIT-labeled) is self-declared with no documented upstream
  provenance despite the dataset name, and turned out to contain
  meaningful noise (English/Hindi function words, fragments); several
  larger candidates were excluded outright (a CC0-labeled electoral-roll
  dataset whose actual access terms are research-only/non-commercial; a
  ~28k-name GitHub gist set with no license at all). Bundled anyway with
  the provenance gap and every exclusion documented in `data/indian_names.py`,
  per an explicit decision this session rather than silently overstating
  coverage.

  **L2 (structural):** new patterns in `patterns.py` -- PERSON_NAME
  honorifics (Shri/Sri/Smt/Kum/Mr/Mrs/Ms/Dr/Prof/Late + capitalised run),
  relational markers (S/o, D/o, W/o, C/o, "son of"/"daughter of"/"wife of",
  emitting both the subject's and the relative's name as separate
  candidates), dotted initials ("K.S. Rao", high confidence) and undotted
  trailing initials ("Srinivasan K", context-gated -- too ambiguous
  standalone), form-field labels ("Name:", "Applicant", "Customer Name");
  INDIAN_ADDRESS unit markers (H.No./Flat/Plot/Sector/Block/Phase/Door No.
  + number), landmark-relative phrases (near/opposite/behind/beside +
  proper noun), locality-word suffixes (Nagar/Colony/Vihar/Puram/Layout/
  Extension/Marg), and **mutual PIN_CODE reinforcement** (a place hit
  within 20 chars of a PIN-shaped number is boosted 0.3 -> 0.65 in
  `gazetteer.py`; PIN_CODE's own context keywords gained the locality-word
  set for the reverse direction). Two documented, deliberately-not-"fixed"
  precision limitations: "Dr. Reddy's" (the pharma brand) is structurally
  indistinguishable from "Dr. Reddy" the person; a capitalised common noun
  after "near"/"behind"/etc. is indistinguishable from a real landmark --
  both need real-world entity knowledge (L3/L4), not more regex.

  **L3 (NLP agreement):** `NerMapping.agreement_boost` (new in
  maskflow-core, see Changed above) wired up for PERSON_NAME via spaCy's
  `PERSON` label (standalone confidence deliberately left at pack-intl's
  existing `0.75` -- see the pack-intl behavior-change note above -- with
  `agreement_boost=0.2`). A GPE/LOC mapping for INDIAN_ADDRESS was
  implemented, measured, and **deliberately dropped**: unlike PERSON_NAME,
  spaCy tagging a place and the gazetteer agreeing it's a place doesn't
  resolve INDIAN_ADDRESS's actual ambiguity (is this bare mention part of
  an address, vs. just a place named in passing) -- it measurably promoted
  plain sentences like "Mumbai is a city in India." past threshold with no
  address context at all. INDIAN_ADDRESS recall beyond L1+L2 is left to a
  future landmark/context gazetteer instead. This pack now depends on
  `maskflow-core[nlp]` (spaCy) unconditionally -- previously spaCy-free.

  **Cumulative L1+L2+L3 report** (`bench/indiapii/report.py`, against a
  small hand-built fixture set under `packs/maskflow-pack-india/tests/
  fixtures/india_l{1,2,3}_samples.py` -- not a general accuracy claim,
  and iterated against directly while building, so treat as "known bug
  classes fixed" rather than production accuracy): PERSON_NAME 79.3%
  precision / 100% recall; INDIAN_ADDRESS 92.9% / 100%. PERSON_NAME's
  remaining false positives are entirely documented, known limitations
  (common-word/name collisions inherited from maskflow-pack-intl's own
  pre-existing PERSON NER, confirmed present even with pack-india NOT
  installed; the "Dr. Reddy's" ambiguity above) -- not new regressions
  from this session's recognizers. Re-run `bench/indiapii/report.py` if
  L4 is ever taken up.
- `maskflow-cli`: `maskflow doctor` -- checks installed maskflow-core/cli/pack
  versions, spaCy + `en_core_web_sm` model presence, `.maskflowrc` validity,
  and prints which entities are consequently enabled/disabled (an NER-backed
  entity like `PERSON_NAME` reports "disabled -- spaCy model unavailable"
  when the model isn't installed; an entity turned off via
  `.maskflowrc`'s `entities.<X>.enabled = false` reports that instead).
  Also flags the still-unimplemented `RedisMappingStore` as an informational
  warning. Exits 0 only when every check passes. Adds `rich` as a
  `maskflow-cli`-only dependency for the table output.
- `maskflow-cli`: `maskflow explain "<text>"` -- shows, span by span, why
  each piece of text was (or wasn't) detected as PII: the pattern/NER hit,
  checksum result, context boost, and the threshold decision behind it.
  Spans that scored below their entity's threshold are listed separately as
  NEAREST MISSES, along with the `.maskflowrc` threshold change that would
  have caught them. Matched text is truncated to 8 characters by default
  (`--full` shows the entire match) -- never printed unbounded, per this
  repo's no-raw-PII-in-output rule. Supports `--config`/`--set` like
  `maskflow config`, so explanations reflect the same resolved config a
  real `mask()` call would use.
- `maskflow-core`: `detect()` gained an opt-in `return_rejected` keyword
  (default `False`, zero behavior/cost change for existing callers) that
  changes the return shape to `(accepted, rejected)`, where `rejected` is
  every candidate span dropped for scoring below its entity type's
  threshold in the resolve pass. `Span.explanation` changed from
  `list[str]` to `list[ExplanationStep]` (a new structured dataclass:
  `rule`, `outcome`, `delta`, `detail`) so decision trails can be rendered,
  serialized, or asserted on by field instead of by substring match. This
  is the core support `maskflow explain` is built on.
## [core 0.8.0, pack-india 0.5.1, pack-intl 0.3.2, sdk 0.9.1, cli 0.7.1, evidence 0.1.1] - 2026-09-09

### Added

- **`maskflow-core` `0.7.0` -> `0.8.0`** -- negative-context suppression
  hook ([#63](https://github.com/maskflow/maskflow/issues/63)). The
  confidence formula's `- negative_context` half is now implemented:
  `context.apply_negative_context()` lowers a candidate's confidence by
  `PENALTY` (`0.3`, floored at `0.0`) when a registered negative keyword for
  its type sits within the same `WINDOW` as the positive
  `apply_context_boost()` check. `register_pattern()`,
  `register_custom_recognizer()`, `register_ner_recognizer()` and the
  matching `PatternRecognizer` / `GazetteerRecognizer` / `NlpRecognizer`
  classes gain an optional `negative_context_keywords` argument; core ships
  none of its own, exactly like `context_keywords`. Applied after the
  positive boost and regardless of whether a checksum validator passed --
  so a checksum-valid *synthetic* identifier next to "example"/"sample" can
  be pulled below threshold and dropped. Adds a `negative_context`
  `ExplanationStep` (`not_configured` / `suppressed` / `no_match`) to every
  candidate's trail. Additive and backward-compatible; no behavior change
  until a pack registers negative keywords. **Closes
  [#63](https://github.com/maskflow/maskflow/issues/63).**
- `maskflow-pack-india` `0.5.0` -> `0.5.1`: registers negative-context
  keywords (`_NEGATIVE_CONTEXT`) for every entity type it owns -- English,
  Devanagari (`उदाहरण`, `नमूना`, `काल्पनिक`, `फर्जी`, ...) and Hinglish
  transliterations (`udaharan`, `farzi`, `nakli`, ...) of "example / sample /
  specimen / dummy / test data / for illustration". Type-independent, set
  once per `PIIType` (unioned with any co-installed pack's keys) rather than
  per pattern. Effect: a shape-only, context-gated match (`PIN_CODE 0.3`,
  `INDIAN_MOBILE 0.35`, `BANK_ACCOUNT_IN 0.3`, `ABHA_NUMBER 0.35`,
  `AADHAAR_MASKED 0.45`) introduced as an example is now pulled back under
  threshold and left unmasked, while a checksum-validated Aadhaar/PAN/GSTIN
  stays above it. Requires `maskflow-core>=0.8.0` (imports the new
  `NEGATIVE_CONTEXT_KEYWORDS`).
- `maskflow-pack-intl` `0.3.1` -> `0.3.2`: registers the English
  illustrative-value negative-context keywords for every type it owns.
  Suppresses `SSN_PLAIN` and a bare IPv4 next to "for example" / "sample";
  `EMAIL`, dashed `SSN`, `AWS_KEY` and other high-confidence matches are
  unaffected. Requires `maskflow-core>=0.8.0`.

### Fixed

- `maskflow-core`: the ReDoS adversarial probe
  (`maskflow_core.config.redos`) no longer counts interpreter-`spawn`
  startup latency against a pattern's time budget
  ([#88](https://github.com/maskflow/maskflow/pull/88)). It previously did
  `proc.join(timeout=0.5s)` on a freshly spawned child, so on a slow or
  loaded machine the interpreter boot alone could exceed the budget and a
  trivial pattern (`\bEMP-\d{6}\b`) was falsely rejected as catastrophic
  backtracking -- surfacing as an intermittent `config validate` / `config
  show` exit-1 in CI. The child now times each `re.search()` call itself
  and reports the elapsed seconds; the parent flags a pattern only when a
  *match* exceeds the budget (`_PROBE_MATCH_BUDGET_SECONDS`, 0.2s) or a
  probe never reports back. All probes for one pattern now share a single
  child process rather than one spawn each (~0.13s vs ~1s per pattern).

### Changed

- **`maskflow-core` dependency bounds widened for the `0.8.0` bump** (no
  code change in these three -- the bump exists purely to publish the
  widened bound as a new release, same as the `sdk 0.4.0 -> 0.5.0` /
  `cli 0.3.0 -> 0.4.0` bump for `core 0.6.0`):
  - `maskflow-pack-india` `0.5.0` -> `0.5.1` and `maskflow-pack-intl`
    `0.3.1` -> `0.3.2`: `maskflow-core[nlp]` bound `>=0.6.0,<0.8` ->
    `>=0.8.0,<0.9` (they import `NEGATIVE_CONTEXT_KEYWORDS`, new in `0.8.0`).
  - `maskflow-sdk` `0.9.0` -> `0.9.1`: `maskflow-core` bound
    `>=0.7.0,<0.8` -> `>=0.7.0,<0.9`.
  - `maskflow-cli` `0.7.0` -> `0.7.1`: `maskflow-core[yaml]` bound
    `>=0.6.0,<0.8` -> `>=0.6.0,<0.9`.
  - `maskflow-evidence` `0.1.0` -> `0.1.1`: `maskflow-core` bound
    `>=0.7.0,<0.8` -> `>=0.7.0,<0.9`.
  - `maskflow-gateway` / `maskflow-litellm` / `maskflow-langchain` /
    `maskflow-llamaindex` / `maskflow-mcp` are unaffected -- they depend on
    `maskflow-sdk` (`>=0.9.0,<0.10`, satisfied by `0.9.1`), not on
    `maskflow-core` directly.

## [evidence 0.1.0, gateway 0.2.0, cli 0.7.0, core 0.7.0, sdk 0.9.0, pack-india 0.5.0, pack-intl 0.3.1] - 2026-09-09

**R5 · Evidence, item 1 (issue
[#41](https://github.com/maskflow/maskflow/issues/41), PR
[#86](https://github.com/maskflow/maskflow/pull/86)).** An open,
metadata-only record of *what was masked* -- never the values. The
compliance-clause mapping, retention default, and the dashboard's
"controls covered" framing are deferred to issue
[#42](https://github.com/maskflow/maskflow/issues/42).

Publishing order: `pack-intl` / `pack-india` first (they gate the
`maskflow-core` upper bound), then `core`, then `sdk` / `evidence`, then
`gateway` / `cli`.

### Added

- **`maskflow-evidence` `0.1.0`** -- a new package.
  - **`EvidenceEvent`** -- one event per `(entity_type, recognizer, action)`
    per masking call: `entity_type`, `count`, `score`, `recognizer`,
    `action` (`masked`/`redacted`/`surrogate`/`passed`), `service`,
    `environment`, `session_id`, `provider`, `model`, `pack_version`,
    `engine_version`, plus a generated `event_id` and `ts`. **Every field
    is a bounded slug, a bounded number, or a closed enum -- there is no
    `str` field a caller fills in freely**, so a detected value cannot
    appear. Enforced by `guard.assert_schema_is_metadata_only()` (static
    field-set + validator audit), a Hypothesis property test, an AST check
    that `derive.py` never reads `Span.text` / `MappingEntry.original`, and
    a `detect_patterns_only()` pass (`guard.assert_no_pii`) over events
    emitted from a PII corpus. `-m leak` gate, rerun as a distinct CI check.
  - **Emitters** -- one `Emitter` interface, several self-hosted backends:
    `stdout`, `file` (size-rotated JSON lines), `syslog` (all stdlib),
    `webhook` (`maskflow-evidence[webhook]`), `otlp`
    (`maskflow-evidence[otlp]`). **Off by default** (`NullEmitter`); an
    emit failure is logged and dropped, never raised into the masking call.
  - **`derive`** -- `events_from_spans()` / `events_from_mapping()` build
    events from a `detect()` result or a session `Mapping` without ever
    touching a value; `EventContext` carries the per-call context.
  - **Config** -- a `.maskflowrc` `[evidence]` section (`enabled` = false by
    default, `sink`, `path`, `url`, `service`, `environment`, …), validated
    by `maskflow-core`; `EvidenceConfig.from_rootconfig()` /
    `.from_env(prefix)` resolve it.
  - Ships `py.typed`, `contrib/grafana-dashboard.json` (panels only),
    `docs/evidence.md` (schema, **what is deliberately not collected**,
    setup guide), `release-evidence.yml` on `evidence-v*` tags, a dedicated
    CI job.
- **`maskflow-gateway` `0.1.0` -> `0.2.0`** -- **evidence emission.** When
  `[evidence]` is enabled (via a discoverable `.maskflowrc` or
  `MASKFLOW_GATEWAY_EVIDENCE_*` env vars, which win), every proxied request
  emits one metadata-only `EvidenceEvent` per detected type. The client
  `X-Maskflow-Session` header is **hashed** into `session_id`, never emitted
  raw. New Prometheus counter `maskflow_evidence_emitted_total{sink}`. Off
  by default; emission failures never affect a proxied request. Depends on
  `maskflow-evidence` (stdlib sinks only in the base install).
- **`maskflow-cli` `0.6.0` -> `0.7.0`** -- `maskflow explain --evidence` /
  `--evidence-file PATH` emits evidence events for a run (near-misses become
  `action="passed"`). Needs the opt-in `maskflow-cli[evidence]` extra
  (imported lazily -- every other command runs without it, and so does the
  standalone binary). `maskflow doctor` gains an `evidence` readout line.

### Changed

- **`maskflow-core` `0.6.0` -> `0.7.0`** -- additive, backward-compatible
  (`mask()` / `unmask()` / `mask_and_call()` and the round-trip guarantee
  untouched):
  - `MappingEntry` gains optional `score` / `recognizer` fields (metadata
    about the detection, not the value), populated by `mask_with_policy()`
    and round-tripped by `Mapping.to_json()` / `from_json()` **only when
    set** -- an older serialized mapping loads unchanged.
  - New `[evidence]` `.maskflowrc` section + `EvidenceSection` schema (all
    defaults off), so `maskflow config validate` accepts it. Core validates
    the knobs only; the emitter lives in `maskflow-evidence`.
- **`maskflow-sdk` `0.8.0` -> `0.9.0`** -- `Session` threads the originating
  span's `score` / `recognizer` onto every `MappingEntry` it records, so the
  gateway's evidence events are full-fidelity. Requires `maskflow-core`
  `>=0.7.0`. No API change.
- **`maskflow-pack-intl` `0.3.0` -> `0.3.1`** -- no code change; the
  `maskflow-core` bound is widened from `<0.7` to `<0.8` so it composes
  with `maskflow-core` `0.7.0` (without this the whole `sdk` / `gateway` /
  `cli` line is unresolvable).
- **`maskflow-pack-india` `0.4.0` -> `0.5.0`** (issue #28 closeout): the
  `maskflow-core` bound is likewise widened to `<0.8`, and two bundled
  reference datasets grow via the refresh script.
  - `IFSC_BANK_CODES` 56 -> 94 entries: cross-checked against `razorpay/ifsc`'s
    public-domain data -- every in-scope code this pack's manual curation had
    missed (foreign / private / small-finance / payments / local-area banks,
    plus 3 merged/retired PSU codes); `ESFB`'s stale comment corrected
    ("ESAF" -> "Equitas"), the value unchanged.
  - `INDIAN_CITIES` 368 -> 554 entries: unions the existing Wikipedia list
    with Census 2011 towns of population >= 100,000, clearing the #28
    "top-500" target.
  - **Behavior change** (additive, no API change): IFSC / VEHICLE_REG /
    DRIVING_LICENCE structural validation and the INDIAN_ADDRESS L1
    gazetteer now accept/match values they previously rejected/missed --
    e.g. an IFSC starting `IPPB` / `ESFB` / `USFB`, and 186 more city names
    as address context.
  - Still open (see `docs/data-refresh.md` and the #28 follow-up issues):
    the `PERSON_NAME` (Indian) 150k-name gazetteer target and India-specific
    negative-context terms.

## [core 0.3.0, pack-intl 0.2.0, sdk 0.2.0] - 2026-08-21

### Added

- `maskflow-core`: `.maskflowrc` configuration file support --
  `maskflow_core.config`, TOML (primary, stdlib `tomllib`/`tomli`), YAML
  (optional `maskflow-core[yaml]` extra), and JSON. Config resolves
  through five precedence levels (schema defaults < user file
  `~/.config/maskflow/config.toml` < project file, discovered by walking up
  from cwd and stopping at the repo root < environment variables
  (`MASKFLOW_*`) < CLI `--set`/`--config`), tracking per-field provenance.
  Validation (hand-rolled dataclasses + validators -- no pydantic, to keep
  core's footprint essentially unchanged) rejects unknown keys with a
  did-you-mean suggestion (`entities.PAN.threshod` -> "did you mean
  'threshold'?") and reports every problem found in one pass, annotated
  with file:line when known. User-supplied regex (`custom.<NAME>.pattern`,
  `exclusions.patterns`) goes through a ReDoS safety check (static shape
  check + timeboxed adversarial probe) before being accepted. See
  `docs/configuration.md` for the full schema and precedence reference.
- `maskflow-core`: `detect()` and `mask_with_policy()` gain five
  keyword-only params (`per_entity_threshold`, `disabled_types`,
  `extra_patterns`, `exclusion_values`, `exclusion_patterns`) -- how
  resolved `.maskflowrc` config reaches detection/masking
  (`maskflow_core.config.engine.compile_config()`). Every one defaults to
  "no effect", so existing calls are unmodified both in output and in the
  code path they run; `maskflow_core.masking.mask()` itself is untouched.
  Also exports `surrogate_substitute` (renamed from the former private
  `_surrogate_substitute`, no behavior change).
- `maskflow-cli` (new package, 0.1.0): `maskflow config validate` and
  `maskflow config show [--resolved]`, built on `maskflow_core.config`.
  `exclusions.values` is redacted in all CLI output.
- `maskflow-core`/`maskflow-pack-intl`: added `py.typed` markers (PEP 561)
  so downstream packages can be type-checked against them without
  `ignore_missing_imports` -- no behavior change.
- `maskflow-sdk`: `mask()`, `mask_and_call()`, `session()`/`async_session()`
  all gain an optional `config=` parameter (a `maskflow_core.config.
  RootConfig`) that changes which entities are detected
  (threshold/enabled/custom patterns/exclusions) and how they're
  substituted (strategy: replace/redact/mask/hash/surrogate).
  `config=None` (the default) uses the ambient `.maskflowrc` discovered
  from the filesystem, cached once per process -- a long-running server
  doesn't re-stat the filesystem on every call; `maskflow.reload_config()`
  forces a fresh discovery. Passing `config=` explicitly bypasses
  discovery entirely, for a library embedded in someone else's
  application. **With no `.maskflowrc` anywhere and no `config=` passed,
  output is byte-identical to before this change** -- proven with a
  10,000-example hypothesis property test
  (`maskflow-core/tests/test_masking.py::
  test_mask_with_policy_default_matches_mask`) asserting
  `mask_with_policy(text, MaskPolicy())` is byte-identical to `mask(text)`
  for arbitrary text and threshold, which is what the config-aware
  `mask()` wrapper delegates to. Non-reversible substitutions
  (redact/mask/hash) are simply omitted from `MaskResult.mapping` rather
  than requiring a type change. `Session` compiles its config once at
  construction (not per call); numeric `mask_json()` leaves keep their
  numeric-surrogate scheme regardless of configured strategy, preserving
  the documented "leaf's JSON type never changes" invariant.
- `maskflow-sdk`: `maskflow.session()` / `maskflow.async_session()` --
  session-scoped masking for multi-turn/multi-tool-call agents. Unlike
  `mask()` (counters and value->token identity reset every call), a
  `Session` keeps that identity stable for its whole lifetime, so the same
  PII value always gets the same `<TYPE_n>` token across separate
  `.mask()`/`.mask_json()` calls instead of each call independently
  restarting its own numbering (see `docs/agent-sessions.md` for the
  concrete before/after). `Session.mask_json()` walks a nested
  dict/list/tuple structure, masking string leaf *values* only -- dict keys
  are never touched, and a PII-shaped integer leaf is replaced with a
  same-digit-count integer surrogate rather than a schema-breaking string,
  so a masked tool-call payload keeps its original JSON shape. Sessions are
  closeable (`with maskflow.session() as s: ...`, or `s.close()`) and
  TTL-bounded (`ttl_seconds`, default 3600); either purges the mapping, and
  any further call raises the new `SessionClosedError` instead of silently
  no-op'ing. `AsyncSession`/`async_session()` wrap the same `Session` via
  `asyncio.to_thread` with no changes to core. Neither `Session` nor
  `AsyncSession` is thread-safe -- documented explicitly rather than
  silently assumed. No change to `mask()`/`unmask()`/`mask_and_call()`.

### Fixed

- `maskflow-core`: `pytest -m leak` run on its own used to deselect every
  test except the leak-gate assertion itself, so `LEAK_POOL` -- filled only
  by whatever ran earlier in the same process -- stayed empty and the gate
  passed trivially even with an active PII leak elsewhere in the code
  (verified: adding a deliberate `logger.debug(span.text)` to a recognizer
  and running `pytest -m leak` alone did not fail). `pytest_configure` in
  `maskflow_core.testing` now neutralizes any `-m`/markexpr mentioning
  "leak" so the whole session still runs -- the marker is for ordering
  (leak-gate test runs last) and identification, not selection.

### Changed

- `maskflow-core` / `maskflow-sdk` / `maskflow-pack-intl`: raised the minimum
  supported Python from 3.9 to 3.10 (`requires-python = ">=3.10"`). Python
  3.9 reached upstream end-of-life on 2025-10-05 and no longer receives
  security patches; it was also the direct cause of CI's slowest jobs
  (~15 min) -- spaCy's `blis` dependency has no prebuilt wheel for 3.9 on
  several platforms, forcing a from-source build every run. `ci.yml`'s test
  matrix drops 3.9 (and the Windows+3.9 exclude workaround it needed) in
  favor of 3.10/3.11/3.13; `ruff`'s `target-version` and ambient code style
  move to `py310` accordingly (e.g. `Union[X, Y]` -> `X | Y`, `zip()` calls
  now specify `strict=` explicitly, newly enforceable now that all
  supported versions have it).

### Added

- `maskflow-core`: `mask_with_policy(text, policy, min_confidence)` alongside
  the untouched `mask()`/`unmask()`/`mask_and_call()` (`maskflow-sdk`'s
  0.1.0 API is unchanged -- new capability lives entirely in new functions).
  Five substitution strategies, selected per entity type via
  `MaskPolicy(default_strategy, per_entity_strategy)`: `REPLACE` (the
  existing typed-placeholder behavior), `REDACT` (constant
  `[REDACTED_TYPE]` marker), `MASK` (partial reveal, e.g. `XXXX XXXX 9012`,
  configurable via `MaskConfig`), `HASH` (HMAC-SHA256, stable per value,
  keyed via `HashConfig` or `MASKFLOW_HASH_KEY`), and `SURROGATE` (a
  plausible fake of the same type, via `register_surrogate_generator()`;
  falls back to `REPLACE` for any type with no registered generator).
  `REPLACE`/`SURROGATE` are reversible via the same `unmask()`; `REDACT`/
  `MASK`/`HASH` are intentionally one-way. `mask_with_policy()` returns a
  `PolicyMaskResult` whose mapping is a `Mapping` (token -> `MappingEntry`),
  not a plain dict -- `MappingEntry.original` is repr-excluded like
  `Span.text` (rule 1).
- `maskflow-core`: `MappingStore` protocol plus `InMemoryMappingStore`
  (TTL-expiring, process-local, the default), `EncryptedFileMappingStore`
  (AES-GCM at rest, key from `MASKFLOW_MAPPING_KEY` or passed explicitly --
  requires the new optional `maskflow-core[store]` extra), and
  `RedisMappingStore` (interface-only stub this round -- every method
  raises `NotImplementedError`). Masking itself stays pure/stateless; a
  `MappingStore` is an opt-in way for a caller to persist a `Mapping`
  across requests/processes.
- `maskflow-core`: 10,000-example Hypothesis property test
  (`unmask(mask(t).masked_text, mapping) == t` for arbitrary `st.text()`)
  plus explicit empty-string/index-0/final-index/combining-character cases,
  proving CLAUDE.md's "round-trip sacred" guarantee (rule 5) rather than
  just asserting it. Offsets are documented as Python `str` code-point
  offsets throughout (`detect()`/`mask()`/`mask_with_policy()`), not byte
  offsets -- consistent, and safe for non-ASCII PII.
- `maskflow-core` / `maskflow-pack-intl`: whole-session leak gate
  (`maskflow_core.testing`, `pytest -m leak`) -- captures every log record
  and exception raised during a package's test session and asserts none of
  its known PII fixture values ever appeared in either, in addition to the
  existing per-class repr checks. Runs as part of each package's normal
  `pytest` step in CI (the marker doesn't exclude, so no separate CI job
  was needed).
- `maskflow-pack-intl`: `Strategy.SURROGATE` generators for EMAIL, PHONE,
  SSN, CREDIT_CARD, IBAN, PERSON_NAME, and ADDRESS, each drawing from a
  documented reserved/invalid range or embedded synthetic corpus (see the
  package README's surrogate table) so a generated value never collides
  with something a real issuer could plausibly assign.

### Changed

- `maskflow-core`: `mask()` now reuses the same `<TYPE_n>` token for a
  repeated identical PII value within one call, instead of minting a new
  numbered token for every occurrence (CLAUDE.md design decision #3,
  "same value -> same token per session"). Round-trip behavior is
  unaffected either way (`str.replace()` already restores every occurrence
  of a token); output for text with no repeated values is unchanged.
- `maskflow-core`: replaced the ad hoc per-recognizer overlap merge with a
  central `SpanSet.resolve(config)` pipeline (`maskflow_core.spanset`).
  `Finding` is renamed `Span` (`type`/`value` fields renamed
  `entity_type`/`text`); every span now also carries `recognizer` and an
  `explanation` trail. Overlap resolution supports a configurable per-entity
  policy -- `STRICT` (default, no overlaps survive), `CONTAINED` (a more
  specific nested span wins over a same-status containing one), `MERGE`
  (adjacent same-type spans separated by whitespace/a punctuation character
  join into one) -- while the existing invariant is unchanged: a
  checksum-validated span never loses to an overlapping unvalidated one.
  Detection now runs a tier-0 excision pass -- confidently-resolved regex
  spans are blanked out (same-length filler, so char offsets are preserved)
  before the NER pass runs over the remainder, rather than NER scanning raw
  PII text. No change to `mask()`/`unmask()`/`mask_and_call()` signatures or
  behavior. `maskflow-sdk` and `maskflow-pack-intl` updated accordingly
  (`Finding` -> `Span` in `maskflow-sdk`'s exports too).

## [sdk 0.1.1] - 2026-08-20

### Changed

- `maskflow-sdk`: now depends on `maskflow-core>=0.2.0,<0.3` and
  `maskflow-pack-intl>=0.1.0,<0.2` (previously `maskflow-core>=0.1.0,<0.2` with
  recognizers bundled directly into core). No public API change --
  `mask()`/`unmask()`/`mask_and_call()` are identical -- this just moves
  `pip install maskflow-sdk` onto the split core/pack-intl architecture
  published in `core 0.2.0, pack-intl 0.1.0` below.

## [core 0.2.0, pack-intl 0.1.0] - 2026-08-19

### Changed

- **Workspace restructure**: the repo is now a real [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
  rooted at `pyproject.toml`, with members under `packages/*` and `packs/*`. `core/` moved to
  `packages/maskflow-core`, `sdk/python/` moved to `packages/maskflow-sdk`, and
  `packages/detection/` moved to `packages/maskflow-js` (npm package name unchanged --
  still publishes as `@maskflow/detection`). No published-artifact behavior changes; import
  paths (`from maskflow_core import ...`, `from maskflow import ...`) are unaffected.
- `maskflow-core` no longer ships any recognizers -- `patterns.py` and the PERSON_NAME/
  DATE_OF_BIRTH NER logic moved to a new package, **`maskflow-pack-intl`**, which registers
  all 12 original types (email, phone, SSN, credit card, IP, AWS/API keys, JWT, IBAN, address,
  person name, date of birth) against core on import. `maskflow-sdk` now depends on
  `maskflow-pack-intl` automatically, so `pip install maskflow-sdk` behaves identically to
  before -- this only matters for code importing `maskflow_core` directly without a pack.
- `maskflow-core`: `registry.py` gained `register_ner_recognizer()` alongside the existing
  `register_pattern()`, so spaCy-label-based recognizers (like PERSON_NAME/DATE_OF_BIRTH) are
  now pack content too, registered the same way regex-based ones are. Both registration
  functions accept an optional `context_keywords` argument, replacing the previously-hardcoded
  `CONTEXT_KEYWORDS` table.
- `maskflow-core`: spaCy moved from a required dependency to an optional one
  (`maskflow-core[nlp]`). Without it installed, the NER pass is skipped with a single warning
  and pattern-based recognizers are unaffected.

### Fixed

- `maskflow-core` / `maskflow-pack-intl`: fixed a latent Python 3.9 incompatibility (`X | None`
  return/parameter annotations evaluated eagerly instead of deferred) that would have broken
  on 3.9 the first time CI actually tested that version -- added `from __future__ import
  annotations` to the affected modules.

- `maskflow-core`: `Finding.value` no longer appears in default `repr()`
  output, and test-failure messages no longer interpolate raw sample text or
  matched values -- closes a PII leak surface in test/debug output. Registered
  the `benchmark`/`leak` pytest markers referenced by CLAUDE.md's commands.
- `maskflow-core` / `@maskflow/detection`: bounded the two unbounded `\w*`
  quantifiers in the generic-secret-assignment regex (was O(n^2) on long
  word-runs with no `:`/`=`).

- `maskflow-core` / `@maskflow/detection`: `mask()` now pre-scans input text
  for placeholder-lookalike substrings (e.g. a prompt that already contains
  `<EMAIL_1>`) and falls back to a nonce-suffixed token on collision.

### Added

- `maskflow-core` / `@maskflow/detection`: unicode/emoji/RTL/zero-width
  round-trip test coverage for `mask()`/`unmask()`.
- `maskflow-core` / `@maskflow/detection`: `Finding.validated` -- true when a
  structural validator (Luhn, IBAN mod-97, SSN area-code check) confirmed the
  match. Central overlap resolution now sorts by (validated desc, confidence
  desc, length desc, start asc), so a checksum-validated span always beats an
  overlapping unvalidated one.
- `maskflow-core`: `PIIType` is now an open registry (`PIIType.register(...)`)
  instead of a closed `Enum`, and `register_pattern()` lets a future pack
  (e.g. `maskflow-pack-india`) add new PII types and recognizer rules without
  editing `maskflow-core` itself. Existing built-in types and their `.value`/
  equality/`isinstance` behavior are unchanged.

## [0.1.0] - 2026-08-06

### Added

- `maskflow-core`: PII detection and reversible masking engine. Three-layer detection pipeline
  (regex + structural validation, keyword-context confidence boosting, spaCy NER) covering 12 PII
  types: email, phone, SSN, credit card, IPv4/IPv6, AWS access key, API key/generic secret, JWT,
  IBAN, street address, person name, date of birth.
- `maskflow-sdk`: Python SDK built on `maskflow-core`, with `mask_and_call` for masking a prompt,
  calling any LLM, and unmasking the response.
- `@maskflow/detection`: TypeScript port of the regex/structural detection layer.

[unreleased]: https://github.com/maskflow/maskflow/compare/sdk-py-v0.1.1...HEAD
[sdk 0.1.1]: https://github.com/maskflow/maskflow/compare/sdk-py-v0.1.0...sdk-py-v0.1.1
[core 0.2.0, pack-intl 0.1.0]: https://github.com/maskflow/maskflow/compare/core-v0.1.1...core-v0.2.0
[0.1.0]: https://github.com/maskflow/maskflow/releases/tag/v0.1.0
