# `maskflow audit` — find and prove unmasked LLM egress paths

`maskflow scan` answers the retrospective question — what PII already left,
read from your logs. `maskflow audit` answers the forward one, read from
your source:

> **Where in this codebase can personal data reach an LLM, and is that path
> masked?**

It walks a source tree, enumerates every call by which text leaves for a
provider, classifies each one as masked or not, and traces each payload back
to the database column, request field or file it came from. Your code is
**parsed, never executed**.

```
maskflow audit [PATH] [options]
```

**Want to see it first?** Six realistic applications, with committed
expected results, live in [`audit-fixtures/`](../audit-fixtures/):

```bash
uv run maskflow audit audit-fixtures/01-fastapi-support-copilot
```

```
0 of 1 LLM egress paths masked
1 unmasked

UNMASKED             app.py:39  openai-client · d823752cba8f
                     from db_column:aadhaar, db_column:body (+4) · conf: high

Canaries were not run, so every finding above is predicted, not proven.
wrote audit.json
```

(`uv run` invokes the CLI from the workspace venv — drop it if `maskflow-cli`
is on your `PATH`.)

## Install

```bash
pip install 'maskflow-cli[audit]'
```

The `[audit]` extra is opt-in, so a bare `pip install maskflow-cli` and the
standalone binary stay small and carry no YAML or AST machinery. Every other
command works without it; `maskflow audit` without it prints the install line
and exits 1.

> **Runs entirely locally. Nothing is transmitted.** No source, no findings,
> no report is ever sent to MaskFlow or anywhere else. The audit makes no
> network request at all.

## What it looks for

The sink registry is **data**, not code —
[`sinks/registry.yaml`](../packages/maskflow-audit/src/maskflow_audit/sinks/registry.yaml).
Adding a provider is a YAML edit and a test, not a change to the analyser.

| Category | Covered |
|---|---|
| `llm_sdk` | `openai` (current + pre-1.0), `anthropic`, `google-genai` / `vertexai`, `litellm`, `cohere`, `mistralai` |
| `framework` | LangChain chat/LLM/embedding classes and chains, LlamaIndex LLMs, query engines and embeddings |
| `raw_http` | `requests` / `httpx` / `aiohttp` where the URL resolves to a known provider host |
| `vector_write` | Pinecone, Qdrant, Chroma, Weaviate, pgvector |
| `observability` | Langfuse, LangSmith, Helicone — exporters that carry the prompt |
| `mcp` | MCP servers whose tool results become model context |

Embedding calls are included deliberately: an embedding of a KYC document is
still that document leaving the process.

## Masking status

Each flow gets exactly one status, in this precedence order.

| Status | Meaning |
|---|---|
| `masked_via_mask_call` | the payload demonstrably came from `mask()` — including through an f-string, a `.format()`, a concatenation, or a `messages=[{"content": …}]` list, or wrapped in `mask_and_call()` |
| `masked_via_gateway_base_url` | the client is pointed at a **recognised** MaskFlow gateway |
| `masked_via_integration` | `maskflow-litellm` / `-langchain` / `-llamaindex` / `-mcp` wraps **this sink's** framework |
| `unmasked` | the payload argument was found and nothing guards it |
| `unknown` | we could not tell — see below |

### Why `unknown` exists, and why it is not a cop-out

The two ways to be wrong are not symmetric. Calling a guarded path unmasked
wastes an afternoon. Calling an unguarded path masked is the failure this
tool exists to prevent. So every rule either proves a guard or declines to.

The honest hard case is the gateway. MaskFlow's gateway is deliberately
OpenAI/Anthropic *path*-compatible and has **no reserved hostname**, so

```python
client = OpenAI(base_url="http://localhost:8000/v1")
```

is indistinguishable from any other local proxy by reading source alone. A
custom `base_url` is therefore treated as proof of nothing. It counts as a
guard only alongside a MaskFlow marker in the same file — a `maskflow`
hostname, an `X-Maskflow-Session` header, a `MASKFLOW_GATEWAY_*` variable —
and otherwise the flow is `unknown`, with the report telling you to confirm
by probing `GET /v1/entities` on that host. A client with **no** `base_url`
is unambiguous: that is direct egress.

Likewise, a `requests.post` whose URL is built at runtime is not reported as
a provider call at all. The alternative is a report listing every HTTP call
in your repository.

## Source tracing

A finding that names a cause is worth far more than one that names a line, so
each payload is traced backwards through assignments in its own function to
the DB column, request field, file read, tool result or parameter it came
from. `mask()` is transparent to this trace — "the `aadhaar` column is masked
before it is sent" is more useful than "something called `mask()`".

Confidence is reported per flow: `high` only when a named origin was
recovered, down to `unknown` when nothing was.

Only **identifiers** are ever recorded — a column name, a field name, a
callee name. The contents of a string literal are never recorded, so a
hard-coded value in the audited codebase cannot ride into the report.

## The report

`audit.json` carries a `schema_version` as its first key, so a consumer — or
a future `--ci` baseline — can refuse a file it does not understand. It
holds the coverage headline, every flow with its status, reason, sources and
explanation, breakdowns by category/provider/status, the files that could not
be parsed, and a methodology block with detector versions, the sink
inventory, and the limits below.

The report contains **no raw value, no string literal's contents, and no line
of your source** — it is identifiers and counts only. That is enforced by a
leak gate in CI which audits a tree seeded with synthetic identifiers in
constants, dicts, defaults, docstrings and comments, and asserts none of them
survives into any output format under casefolding, separator stripping and
all four unicode normal forms.

Determinism is a property, not a side effect: the same tree produces a
byte-identical report apart from `scope.generated_at`, and the config
fingerprint ignores the checkout path so a CI runner and a laptop agree.

## Measured, not asserted

The audit is scored against the six fixture apps in
[`audit-fixtures/`](../audit-fixtures/), each with a committed
`expected.json` that the test suite checks field by field. The published
numbers come from `make audit-bench`:

| metric | value |
|---|---|
| discovery recall | 100% (8/8 expected flows found) |
| classification accuracy | 100% (8/8 labelled correctly) |

Gated in CI against `bench/baselines-audit.json` with the same 2-point
tolerance the F1 benchmarks use; `make rebaseline-audit` regenerates it.
Six applications is a small corpus and the number should be read that way —
it says the audit is correct on the cases we thought to write, not that it is
correct in general.

They earned their place immediately. Fixture 02 caught a Chroma collection
obtained from `get_or_create_collection()` being invisible (the resolution
chain broke at the factory). Fixture 03 caught maskedness failing to
propagate through a prompt template's `.format()`, which made a correctly
masked chain read as unmasked. Fixture 04 caught the trace depth bound
silently dropping the very column names fixture 01 recovered from the same
SQL.

## Proving it: `--prove`

```bash
maskflow audit . --prove --flows "pytest -q tests/integration"
```

This is the part that makes the promise literal:

1. **Refuse production.** Before anything is written, the environment is
   checked for production markers (`APP_ENV`, a non-local `DATABASE_URL`, a
   `.env` naming production). Seeding a real deployment would be a data
   incident caused by the tool that exists to prevent them, so this is a
   hard gate — `--allow-env` overrides it, loudly.
2. **Generate and self-check canaries.** Synthetic Indian identities built
   on the pack's own surrogate generators, then re-validated against the
   pack's own `validate_*()` functions. A canary MaskFlow would not detect
   proves nothing, so a failure here aborts the run rather than producing a
   finding.
3. **Seed.** Pluggable adapters write into environment variables, JSON/CSV
   fixtures, local SQLite databases, and a pytest fixture. Every adapter
   records a backup and is reversed in a `finally`, so an interrupted audit
   still leaves your repository exactly as it found it.
4. **Run your command in a subprocess** with the interception hook installed
   via `sitecustomize`, so the patches are in place before your application
   imports its HTTP client.
5. **Intercept.** `httpx`, `requests` and `aiohttp` are patched at their
   lowest choke point. **No request reaches a provider** — each one is
   captured and a canned response in the provider's own shape is returned,
   so your suite keeps passing.
6. **Attribute.** Each escape is matched to a discovered flow using the
   Python stack captured at send time.

A canary found in an outbound payload is a **confirmed leak**, reported with
the entity type, the form it was found in, the destination, and the call path.

### Seeds, never values

The seed defaults to a fresh random draw, so no repository ever accumulates
a PII-shaped constant. It is recorded in the report, and `--seed N`
reproduces an exact run. A generated Aadhaar-shaped number *could* collide
with a real one — it is random digits plus a valid check digit — which is
why canaries never leave a local or test environment and are never
transmitted anywhere.

### Nothing leaks, including out of the audit

The child process runs escape detection itself and writes only metadata:
host, method, library, the stack, and which canary types escaped in which
form. **The request body never reaches disk.** No canary value appears in
the report, in the terminal, or in the evidence stream.

### How a value is recognised

Raw, case-folded, separator-stripped, all four unicode normal forms, base64,
and — for long digit-only identifiers — as an ordered digit run, which is
what catches a value split across four JSON fields and reassembled on the way
out. Short numeric values are matched only at a digit boundary, so a 6-digit
PIN code inside a timestamp is not a fabricated finding.

## CI: `--baseline` and `--ci`

```bash
maskflow audit --baseline          # writes maskflow-audit.baseline.json; commit it
maskflow audit --ci                # fails the build on a regression
```

`--ci` fails on a **new** unmasked or unknown path, a path that was masked
and no longer is, or a newly confirmed leak. It deliberately does **not**
fail on a path that disappeared, a path whose line moved (flow IDs are not
line-based), or a new path that *is* masked.

A missing baseline is a **skip, not a failure** — a gate that fails before
anyone opted in just gets deleted. Every problem is collected and reported
together rather than failing on the first.

Ships as a composite action in
[`packaging/audit-action/`](../packaging/audit-action/).

## Fixing: `--handoff` and `--fix`

`--handoff` writes `maskflow-audit-tasks.md` — a precise, per-leak task list
for your own coding agent, with the evidence, the three fixes that fit
MaskFlow, and the gates. **No key, no network, no model.** This is the path
most people should take.

`--fix` runs the loop itself against a model you supply. Four hard gates, all
of which must hold before a change is kept:

1. the project's tests pass, unchanged;
2. zero canaries escape on that flow;
3. the round trip still works;
4. the diff adds no network destination, permission, or secret.

The gates are evaluated by the audit, never by the model, and a diff that
touches a test file is rejected before anything is run — **a fix may never
weaken the suite that validates it.** An unverifiable gate counts as a
failure, not a pass. Retries are bounded (default 3), after which the flow is
reported "could not fix automatically" with the reason.

MaskFlow carries no provider dependency and no key: the loop takes a
`(system, user) -> str` callable, the same model-agnostic shape
`mask_and_call()` uses.

## Evidence

`--evidence` emits metadata-only events through the existing
[evidence](evidence.md) emitters: flow counts by masking status, and counts
by entity type for anything a canary proved. Never a file path, never a
column name, never a value — this stream is designed to leave the building.

## What audit does **not** do

Read this section before trusting a clean report. **A clean audit means
nothing known was found — not that nothing exists.**

- **Without `--prove`, nothing is proven.** A plain `maskflow audit` run
  reports *predictions* from static analysis, says so, and reports
  `canaries_run: false` with `confirmed_leaks: 0`. Only `--prove` produces
  evidence.
- **`--prove` only covers what your command runs.** A flow the run never
  reaches is reported `not_exercised`, which means *we learned nothing
  about it* — not that it is safe. Check that status before reading a
  report as clean.
- **Python only.** TypeScript, JavaScript, Go and Java are not covered. The
  registry and resolver are shaped so a tree-sitter front-end can be added
  without touching either the registry or the report, but that is design, not
  delivery.
- **It does not follow calls between functions.** A payload passed two calls
  deep is found, and classified, but its *source* is reported as the
  parameter it arrived on rather than the request field it ultimately came
  from — see fixture 06, whose `expected.json` records exactly that.
- **It cannot see PII split across fields.** An Aadhaar arriving as four
  separate JSON fields and reassembled in the prompt is invisible to static
  reading. This is precisely what canaries exist to catch.
- **It cannot see configuration.** A LiteLLM proxy-side guardrail, or a
  gateway behind a hostname we do not recognise, is not visible from a call
  site. Those flows read `unmasked` or `unknown`.
- **Dynamic dispatch defeats it.** A client built by a factory we cannot
  resolve, or a sink reached through a plugin registry, resolves to `None`
  and is not reported.
- **It does not scan production**, and never will. It reads source.
- **It does not use an LLM to detect anything.** The detection path is
  deterministic and offline, by design.

## Exit codes

| | |
|---|---|
| `0` | the audit completed (a finding is not a failure), or `--ci` passed/skipped |
| `1` | bad arguments, a malformed registry, or **`--ci` found a regression** |
| `2` | the path does not exist, or the environment looks like production |

A finding never fails a plain run. Only `--ci` fails a build.

## Compliance mapping

`audit.json` carries the same `<!-- DPDP_RULE6_APPENDIX -->` marker the scan
report uses, so the substitution recipe in
[`dpdp-rule6.md`](dpdp-rule6.md) works on both. The rendered Rule 6 appendix
arrives with the HTML report in a later milestone.
