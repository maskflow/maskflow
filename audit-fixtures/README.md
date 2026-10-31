# audit-fixtures

Six small but realistic applications that `maskflow audit` is measured
against. Each directory has an `app.py` and an `expected.json`; the audit's
own test suite asserts the report matches `expected.json` exactly.

This is the "measured, not asserted" rule applied to the audit itself. A
detector whose accuracy is only claimed is worth nothing, so the fixtures
include the cases that are *supposed* to be hard, and `expected.json`
records the honest answer — including where the current release cannot
trace a source and says `unknown`.

| # | App | Expected |
|---|---|---|
| 01 | FastAPI support copilot, tickets table -> `openai` | **leaks** |
| 02 | KYC PDF ingestion -> embeddings + Chroma | **leaks** |
| 03 | LangChain chain with Langfuse tracing | **leaks via the trace exporter** |
| 04 | The 01 copilot, wrapped in `mask()` | clean |
| 05 | The 01 copilot, routed through the MaskFlow gateway | clean |
| 06 | PII split across JSON fields, sent two calls deep | **leaks** (source untraced in M1) |

**No real personal data appears anywhere here.** The apps reference column
and field *names*; they contain no identifier values at all, synthetic or
otherwise. The canary harness (M2) is what puts values into a fixture, and
it generates them per run.

The apps are not executed by the M1 test suite — discovery is static, so it
needs no dependency installed. They become runnable under the canary
harness in M2, which is why they are written as working applications
rather than as snippets.
